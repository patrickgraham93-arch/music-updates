import os
import json
import requests
from datetime import datetime, timedelta
import base64
import feedparser
import time

class MusicDataFetcher:
    def __init__(self):
        self.spotify_token = None
        self.client_id = os.environ.get('SPOTIFY_CLIENT_ID')
        self.client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')

    def get_spotify_token(self):
        """Get Spotify API access token"""
        if not self.client_id or not self.client_secret:
            print("❌ WARNING: Spotify credentials not found in environment variables.")
            print("   SPOTIFY_CLIENT_ID:", "SET" if self.client_id else "NOT SET")
            print("   SPOTIFY_CLIENT_SECRET:", "SET" if self.client_secret else "NOT SET")
            print("   Using demo data instead.")
            return None

        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_bytes = auth_string.encode('utf-8')
        auth_base64 = base64.b64encode(auth_bytes).decode('utf-8')

        url = "https://accounts.spotify.com/api/token"
        headers = {
            "Authorization": f"Basic {auth_base64}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"grant_type": "client_credentials"}

        try:
            print("🔑 Requesting Spotify access token...")
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            self.spotify_token = response.json()['access_token']
            print("✅ Successfully authenticated with Spotify API")
            return self.spotify_token
        except requests.exceptions.HTTPError as e:
            print(f"❌ HTTP Error getting Spotify token: {e}")
            print(f"   Response: {response.text}")
            return None
        except Exception as e:
            print(f"❌ Error getting Spotify token: {e}")
            return None

    def get_new_releases(self, limit=50):
        """Get new album releases from Spotify"""
        if not self.spotify_token:
            return []

        headers = {"Authorization": f"Bearer {self.spotify_token}"}
        url = f"https://api.spotify.com/v1/browse/new-releases?limit={limit}"

        try:
            print(f"📀 Fetching new releases from Spotify...")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            albums = response.json()['albums']['items']
            print(f"✅ Found {len(albums)} new releases from Spotify")
            return albums
        except Exception as e:
            print(f"❌ Error fetching new releases: {e}")
            return []

    def search_releases_by_genre(self, genre, limit=50):
        """Search for releases by genre as fallback"""
        if not self.spotify_token:
            return []

        headers = {"Authorization": f"Bearer {self.spotify_token}"}

        # Get current year and last year for better results
        today = datetime.now()
        current_year = today.year

        # Try current year first
        search_query = f"genre:\"{genre}\" year:{current_year}"
        url = f"https://api.spotify.com/v1/search?q={search_query}&type=album&limit={limit}"

        try:
            print(f"🔍 Searching for {genre} releases in {current_year}...")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            albums = response.json()['albums']['items']
            print(f"✅ Found {len(albums)} {genre} albums from search")
            return albums
        except Exception as e:
            print(f"❌ Error searching {genre} releases: {e}")
            return []

    def filter_by_genre_and_recency(self, albums, genre_keywords, days=30, trust_source=False):
        """Filter albums by genre and release date"""
        filtered = []
        cutoff_date = datetime.now() - timedelta(days=days)

        print(f"🔍 Filtering for {genre_keywords} albums from last {days} days...")
        print(f"   Trust source: {trust_source}")

        for album in albums:
            # Parse release date
            release_date_str = album.get('release_date', '')
            try:
                if len(release_date_str) == 4:  # Year only
                    album_date = datetime(int(release_date_str), 1, 1)
                elif len(release_date_str) == 7:  # Year-month
                    album_date = datetime.strptime(release_date_str, "%Y-%m")
                else:  # Full date
                    album_date = datetime.strptime(release_date_str, "%Y-%m-%d")

                # Check if within date range
                if album_date < cutoff_date:
                    continue

            except Exception as e:
                print(f"⚠️  Date parsing error for {album.get('name', 'Unknown')}: {e}")
                continue

            # If we trust the source (genre search), just use date filtering
            if trust_source:
                filtered.append(album)
                continue

            # For new-releases, check artist genres
            artists = album.get('artists', [])
            if not artists:
                continue

            # Get artist genre info (only for new-releases)
            try:
                artist_id = artists[0]['id']
                artist_info = self.get_artist_info(artist_id)
                artist_genres = artist_info.get('genres', [])

                if artist_genres:
                    genres_str = ' '.join(artist_genres).lower()
                    # More flexible matching - any keyword matches
                    genre_match = any(
                        keyword.lower() in genres_str
                        for keyword in genre_keywords.split()
                    )

                    if genre_match:
                        print(f"   ✅ Matched: {album.get('name', 'Unknown')} by {artists[0].get('name', 'Unknown')} - Genres: {artist_genres}")
                        filtered.append(album)
                    else:
                        print(f"   ❌ Skipped: {album.get('name', 'Unknown')} - Genres: {artist_genres}")
                else:
                    # No genres available, include it anyway
                    print(f"   ⚠️  No genres for: {album.get('name', 'Unknown')} - Including anyway")
                    filtered.append(album)
            except Exception as e:
                print(f"   ⚠️  Error checking {album.get('name', 'Unknown')}: {e}")
                # If we can't check, include it
                filtered.append(album)

        print(f"✅ Found {len(filtered)} matching albums")
        return filtered[:10]  # Return top 10

    def get_artist_info(self, artist_id):
        """Get artist information including genres"""
        if not self.spotify_token:
            return {}

        headers = {"Authorization": f"Bearer {self.spotify_token}"}
        url = f"https://api.spotify.com/v1/artists/{artist_id}"

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except:
            return {}

    def get_genre_releases(self, genre_keywords):
        """Get new releases for a specific genre"""
        # First try the new releases endpoint
        all_releases = self.get_new_releases(limit=50)

        # Filter by genre (check artist genres since new-releases isn't genre-specific)
        genre_albums = self.filter_by_genre_and_recency(all_releases, genre_keywords, days=30, trust_source=False)

        # If we don't have enough, try genre search
        if len(genre_albums) < 5:
            print(f"⚠️  Only found {len(genre_albums)} from new releases, trying genre search...")
            search_results = self.search_releases_by_genre(genre_keywords.split()[0], limit=50)
            # Trust the genre search results since Spotify already filtered by genre
            search_filtered = self.filter_by_genre_and_recency(search_results, genre_keywords, days=30, trust_source=True)

            # Combine and deduplicate
            all_albums = genre_albums + search_filtered
            seen_ids = set()
            unique_albums = []
            for album in all_albums:
                if album['id'] not in seen_ids:
                    seen_ids.add(album['id'])
                    unique_albums.append(album)

            genre_albums = unique_albums[:10]

        return genre_albums

    def get_album_details(self, album):
        """Extract relevant album details"""
        artists = ", ".join([artist['name'] for artist in album['artists']])

        search_term = f"{album['name']} {artists}".replace(' ', '+')
        apple_music_url = f"https://music.apple.com/us/search?term={search_term}"

        return {
            'name': album['name'],
            'artists': artists,
            'release_date': album['release_date'],
            'image': album['images'][0]['url'] if album['images'] else '',
            'spotify_url': album['external_urls']['spotify'],
            'apple_music_url': apple_music_url,
            'total_tracks': album.get('total_tracks', 0),
            'album_type': album.get('album_type', 'album')
        }

    def fetch_music_news(self):
        """Fetch music news from various RSS feeds"""
        news_sources = [
            {
                'name': 'Pitchfork',
                'url': 'https://pitchfork.com/rss/news/',
                'category': 'general'
            },
            {
                'name': 'HipHopDX',
                'url': 'https://hiphopdx.com/feed',
                'category': 'hiphop'
            },
            {
                'name': 'Consequence',
                'url': 'https://consequence.net/feed/',
                'category': 'general'
            },
            {
                'name': 'Stereogum',
                'url': 'https://www.stereogum.com/feed/',
                'category': 'rock'
            }
        ]

        all_news = []

        print("📰 Fetching music news from RSS feeds...")
        for source in news_sources:
            try:
                feed = feedparser.parse(source['url'])
                for entry in feed.entries[:5]:
                    pub_date = entry.get('published_parsed') or entry.get('updated_parsed')
                    if pub_date:
                        pub_date = datetime(*pub_date[:6])
                    else:
                        pub_date = datetime.now()

                    # Changed to 3 days for more results
                    if datetime.now() - pub_date <= timedelta(days=3):
                        all_news.append({
                            'title': entry.title,
                            'link': entry.link,
                            'source': source['name'],
                            'category': source['category'],
                            'published': pub_date.strftime('%Y-%m-%d %H:%M'),
                            'summary': entry.get('summary', '')[:200] + '...' if entry.get('summary') else 'Click to read more.'
                        })

                time.sleep(0.5)
            except Exception as e:
                print(f"❌ Error fetching from {source['name']}: {e}")
                continue

        all_news.sort(key=lambda x: x['published'], reverse=True)
        print(f"✅ Found {len(all_news[:20])} news articles")
        return all_news[:20]

    def generate_demo_data(self):
        """Generate demo data when API credentials aren't available"""
        print("⚠️  Generating demo data...")
        return {
            'hiphop': [
                {
                    'name': 'Demo Hip Hop Album',
                    'artists': 'Demo Artist',
                    'release_date': datetime.now().strftime('%Y-%m-%d'),
                    'image': 'https://via.placeholder.com/300?text=Hip+Hop+Album',
                    'spotify_url': '#',
                    'apple_music_url': '#',
                    'total_tracks': 12,
                    'album_type': 'album'
                }
            ],
            'rock': [
                {
                    'name': 'Demo Rock Album',
                    'artists': 'Demo Rock Band',
                    'release_date': datetime.now().strftime('%Y-%m-%d'),
                    'image': 'https://via.placeholder.com/300?text=Rock+Album',
                    'spotify_url': '#',
                    'apple_music_url': '#',
                    'total_tracks': 10,
                    'album_type': 'album'
                }
            ],
            'news': [
                {
                    'title': 'Welcome to Your Music Updates Site!',
                    'link': '#',
                    'source': 'Demo',
                    'category': 'general',
                    'published': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'summary': 'This is demo data. Add your Spotify API credentials to GitHub Secrets to see real music data.'
                }
            ],
            'last_updated': datetime.now().isoformat()
        }

def main():
    print("\n" + "="*60)
    print("🎵 MUSIC DATA FETCHER")
    print("="*60 + "\n")

    fetcher = MusicDataFetcher()

    token = fetcher.get_spotify_token()

    if token:
        print("\n" + "-"*60)
        print("Fetching Hip Hop releases...")
        print("-"*60)
        hiphop_albums = fetcher.get_genre_releases('hip hop rap')
        hiphop_data = [fetcher.get_album_details(album) for album in hiphop_albums]

        print("\n" + "-"*60)
        print("Fetching Alternative Rock releases...")
        print("-"*60)
        rock_albums = fetcher.get_genre_releases('alternative rock indie')
        rock_data = [fetcher.get_album_details(album) for album in rock_albums]

        print("\n" + "-"*60)
        print("Fetching music news...")
        print("-"*60)
        news_data = fetcher.fetch_music_news()

        data = {
            'hiphop': hiphop_data,
            'rock': rock_data,
            'news': news_data,
            'last_updated': datetime.now().isoformat()
        }

        print("\n" + "="*60)
        print("📊 RESULTS SUMMARY")
        print("="*60)
        print(f"✅ Hip Hop Albums: {len(data['hiphop'])}")
        print(f"✅ Rock Albums: {len(data['rock'])}")
        print(f"✅ News Articles: {len(data['news'])}")
        print("="*60 + "\n")
    else:
        print("\n❌ Using demo data due to authentication failure\n")
        data = fetcher.generate_demo_data()

    with open('music_data.json', 'w') as f:
        json.dump(data, f, indent=2)

    print("💾 Data saved to music_data.json\n")

if __name__ == "__main__":
    main()
