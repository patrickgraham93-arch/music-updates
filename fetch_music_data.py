import os
import json
import requests
from datetime import datetime, timedelta
import base64
import feedparser
import time
from urllib.parse import quote

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

    def get_full_album_details(self, album_id):
        """Get full album details including popularity"""
        if not self.spotify_token:
            return None

        headers = {"Authorization": f"Bearer {self.spotify_token}"}
        url = f"https://api.spotify.com/v1/albums/{album_id}"

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except:
            return None

    def enrich_albums_with_popularity(self, albums):
        """Fetch full details for albums to get popularity scores"""
        enriched = []
        print(f"   Fetching popularity scores for {len(albums)} albums...")

        for album in albums:
            full_album = self.get_full_album_details(album['id'])
            if full_album:
                # Merge the full album data with the simplified version
                album['popularity'] = full_album.get('popularity', 0)
                enriched.append(album)
                time.sleep(0.1)  # Rate limiting

        return enriched

    def get_new_releases(self, limit=50):
        """Get new album releases from Spotify"""
        if not self.spotify_token:
            return []

        headers = {"Authorization": f"Bearer {self.spotify_token}"}
        url = f"https://api.spotify.com/v1/browse/new-releases?limit={limit}&market=US"

        try:
            print(f"📀 Fetching new releases from Spotify (US market)...")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            albums = response.json()['albums']['items']
            print(f"✅ Found {len(albums)} new releases from Spotify")

            # Enrich with popularity data
            albums = self.enrich_albums_with_popularity(albums)

            return albums
        except Exception as e:
            print(f"❌ Error fetching new releases: {e}")
            return []

    def search_releases_by_genre(self, genre, limit=50):
        """Search for releases by searching for the genre term directly"""
        if not self.spotify_token:
            return []

        headers = {"Authorization": f"Bearer {self.spotify_token}"}

        # Get current year
        today = datetime.now()
        current_year = today.year

        # Search for albums with year filter - NO genre: prefix (not supported)
        # Just search for the genre term itself
        search_query = f"{genre} year:{current_year}"
        url = f"https://api.spotify.com/v1/search?q={search_query}&type=album&limit={limit}"

        try:
            print(f"🔍 Searching for '{genre}' albums in {current_year}...")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            albums = response.json()['albums']['items']
            print(f"✅ Found {len(albums)} albums from search (before filtering)")

            # Enrich with popularity data
            if albums:
                albums = self.enrich_albums_with_popularity(albums)

            return albums
        except Exception as e:
            print(f"❌ Error searching {genre} releases: {e}")
            return []

    def filter_by_genre_and_recency(self, albums, genre_keywords, days=30, trust_source=False, min_popularity=0):
        """Filter albums by genre, release date, and popularity"""
        filtered = []
        cutoff_date = datetime.now() - timedelta(days=days)

        print(f"🔍 Filtering for {genre_keywords} albums from last {days} days...")
        print(f"   Trust source: {trust_source}")
        if min_popularity > 0:
            print(f"   Minimum popularity: {min_popularity}")

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

            except Exception as e:
                print(f"⚠️  Date parsing error for {album.get('name', 'Unknown')}: {e}")
                continue

            # Check popularity score
            popularity = album.get('popularity', 0)
            if popularity < min_popularity:
                print(f"   ⚠️  Low popularity ({popularity}): {album.get('name', 'Unknown')}")
                continue

            # If we trust the source (genre search), skip strict date filtering
            if trust_source:
                # Only check if it's from this year
                current_year = datetime.now().year
                if album_date.year == current_year:
                    album_info = f"{album.get('name', 'Unknown')} (Pop: {popularity}) - Released: {release_date_str}"
                    print(f"   ✅ Including from search: {album_info}")
                    filtered.append(album)
                else:
                    print(f"   ⚠️  Skipping old album from {album_date.year}: {album.get('name', 'Unknown')}")
                continue

            # For new-releases, check if within date range
            if album_date < cutoff_date:
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
                        print(f"   ✅ Matched: {album.get('name', 'Unknown')} (Pop: {popularity}) by {artists[0].get('name', 'Unknown')} - Genres: {artist_genres}")
                        filtered.append(album)
                    else:
                        print(f"   ❌ Skipped: {album.get('name', 'Unknown')} - Genres: {artist_genres}")
                else:
                    # No genres available, include it anyway
                    print(f"   ⚠️  No genres for: {album.get('name', 'Unknown')} (Pop: {popularity}) - Including anyway")
                    filtered.append(album)
            except Exception as e:
                print(f"   ⚠️  Error checking {album.get('name', 'Unknown')}: {e}")
                # If we can't check, include it
                filtered.append(album)

        # Sort by popularity (highest first)
        filtered.sort(key=lambda x: x.get('popularity', 0), reverse=True)

        print(f"✅ Found {len(filtered)} matching albums (sorted by popularity)")
        if filtered:
            print(f"   Top album: {filtered[0].get('name', 'Unknown')} (Pop: {filtered[0].get('popularity', 0)})")

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

    def search_artist_by_name(self, artist_name):
        """Search for an artist by name to get their Spotify ID"""
        if not self.spotify_token:
            return None

        headers = {"Authorization": f"Bearer {self.spotify_token}"}
        query = quote(artist_name)
        url = f"https://api.spotify.com/v1/search?q={query}&type=artist&limit=1"

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            artists = response.json()['artists']['items']
            if artists:
                return artists[0]['id']
            return None
        except:
            return None

    def get_artist_albums(self, artist_id, limit=50):
        """Get albums for a specific artist"""
        if not self.spotify_token:
            return []

        headers = {"Authorization": f"Bearer {self.spotify_token}"}
        url = f"https://api.spotify.com/v1/artists/{artist_id}/albums?include_groups=album,single&limit={limit}"

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            albums = response.json()['items']
            return albums
        except:
            return []

    def get_releases_from_artist_database(self, genre_category, min_popularity=0):
        """Get releases from curated artist database instead of genre search"""
        # Load artist database
        try:
            with open('artists.json', 'r') as f:
                artist_db = json.load(f)
        except:
            print("❌ Could not load artists.json, falling back to genre search")
            return []

        artist_names = artist_db.get(genre_category, [])
        if not artist_names:
            print(f"❌ No artists found for category: {genre_category}")
            return []

        print(f"🎤 Fetching releases from {len(artist_names)} {genre_category} artists...")

        all_albums = []
        cutoff_date = datetime.now() - timedelta(days=60)
        today = datetime.now()

        print(f"   Today: {today.strftime('%Y-%m-%d')}")
        print(f"   Looking for albums from last 60 days (since {cutoff_date.strftime('%Y-%m-%d')})...")

        for artist_name in artist_names:
            # Search for artist ID
            artist_id = self.search_artist_by_name(artist_name)
            if not artist_id:
                continue

            # Get artist's albums
            albums = self.get_artist_albums(artist_id, limit=20)

            for album in albums:
                # Parse release date
                release_date_str = album.get('release_date', '')
                try:
                    if len(release_date_str) == 4:
                        album_date = datetime(int(release_date_str), 1, 1)
                    elif len(release_date_str) == 7:
                        album_date = datetime.strptime(release_date_str, "%Y-%m")
                    else:
                        album_date = datetime.strptime(release_date_str, "%Y-%m-%d")
                except:
                    continue

                # Check if within 60-day window
                if album_date < cutoff_date:
                    continue

                # Add to results
                all_albums.append(album)

            time.sleep(0.05)  # Rate limiting

        # Enrich with popularity data
        print(f"   Enriching {len(all_albums)} albums with popularity scores...")
        if all_albums:
            all_albums = self.enrich_albums_with_popularity(all_albums)

        # Filter by popularity
        filtered = [a for a in all_albums if a.get('popularity', 0) >= min_popularity]

        # Deduplicate by album ID
        seen_ids = set()
        unique_albums = []
        for album in filtered:
            album_id = album.get('id')
            if album_id and album_id not in seen_ids:
                seen_ids.add(album_id)
                unique_albums.append(album)

        # Sort by release date (newest first), then by popularity
        unique_albums.sort(key=lambda x: (x.get('release_date', ''), x.get('popularity', 0)), reverse=True)

        print(f"✅ Found {len(unique_albums)} albums from artist database")
        if unique_albums:
            print(f"   Most recent: {unique_albums[0].get('name', 'Unknown')} by {unique_albums[0].get('artists', [{}])[0].get('name', 'Unknown')}")

        return unique_albums

    def get_genre_releases(self, genre_keywords, min_popularity=0):
        """Get new releases for a specific genre with proper filtering

        Args:
            genre_keywords: Comma-separated genre keywords to match
            min_popularity: Minimum Spotify popularity score (0-100) to include.
                          Default 0 to show all relevant content.
        """
        # HYBRID APPROACH: Combine new releases + multiple genre searches
        # 1. Get new releases (last 2 weeks typically)
        new_releases = self.get_new_releases(limit=50)

        # 2. Search with multiple genre terms for better coverage
        # For hip-hop: search "rap", "hip hop", "trap"
        # For rock: search "rock", "indie", "alternative"
        search_terms = []
        genre_lower = genre_keywords.lower()

        if 'hip hop' in genre_lower or 'rap' in genre_lower:
            search_terms = ['rap', 'hip hop', 'trap']
        elif 'rock' in genre_lower or 'indie' in genre_lower or 'alternative' in genre_lower:
            search_terms = ['rock', 'indie', 'alternative']
        else:
            # Fallback: use first keyword
            search_terms = [genre_keywords.split(',')[0].strip()]

        # Execute multiple searches
        search_results = []
        for term in search_terms:
            results = self.search_releases_by_genre(term, limit=50)
            search_results.extend(results)

        # 3. Combine and deduplicate by album ID
        seen_ids = set()
        all_releases = []
        for album in new_releases + search_results:
            album_id = album.get('id')
            if album_id and album_id not in seen_ids:
                seen_ids.add(album_id)
                all_releases.append(album)

        print(f"📦 Total unique albums to filter: {len(all_releases)}")

        # Filter by checking artist genres, date, and popularity
        filtered = []
        cutoff_date = datetime.now() - timedelta(days=60)  # 60-day window
        today = datetime.now()

        # Split genre keywords for matching
        genre_keywords_list = [kw.strip().lower() for kw in genre_keywords.split(',')]

        print(f"🔍 Filtering for genres: {genre_keywords}")
        print(f"   Today: {today.strftime('%Y-%m-%d')}")
        print(f"   Looking for albums from last 60 days (since {cutoff_date.strftime('%Y-%m-%d')})...")
        print(f"   Minimum popularity threshold: {min_popularity}")

        for album in all_releases:
            album_name = album.get('name', 'Unknown')

            # Parse release date
            release_date_str = album.get('release_date', '')
            try:
                if len(release_date_str) == 4:
                    album_date = datetime(int(release_date_str), 1, 1)
                elif len(release_date_str) == 7:
                    album_date = datetime.strptime(release_date_str, "%Y-%m")
                else:
                    album_date = datetime.strptime(release_date_str, "%Y-%m-%d")
            except Exception as e:
                print(f"   ⚠️  Date parse error for '{album_name}': {release_date_str}")
                continue

            # Check if within date range
            if album_date < cutoff_date:
                continue

            # Check popularity threshold
            popularity = album.get('popularity', 0)
            if popularity < min_popularity:
                continue

            # Get artist info to check genres
            artists = album.get('artists', [])
            if not artists:
                continue

            try:
                artist_id = artists[0]['id']
                artist_info = self.get_artist_info(artist_id)
                artist_genres = artist_info.get('genres', [])

                if artist_genres:
                    genres_str = ' '.join(artist_genres).lower()
                    # Check if any of our genre keywords match
                    genre_match = any(
                        keyword in genres_str
                        for keyword in genre_keywords_list
                    )

                    if genre_match:
                        print(f"   ✅ Matched: {album_name} (Pop: {popularity}) - Genres: {artist_genres[:3]}")
                        filtered.append(album)

                time.sleep(0.1)  # Rate limiting
            except Exception as e:
                print(f"   ⚠️  Error checking {album_name}: {e}")
                continue

        # Sort by popularity (highest first) but return ALL matching albums
        filtered.sort(key=lambda x: x.get('popularity', 0), reverse=True)

        print(f"✅ Found {len(filtered)} matching albums with popularity >= {min_popularity}")
        if filtered:
            print(f"   Most popular: {filtered[0].get('name', 'Unknown')} (Pop: {filtered[0].get('popularity', 0)})")
            if len(filtered) > 1:
                print(f"   Least popular: {filtered[-1].get('name', 'Unknown')} (Pop: {filtered[-1].get('popularity', 0)})")

        return filtered

    def normalize_string(self, s):
        """Normalize string for comparison by removing special chars and lowercasing"""
        import re
        # Convert to lowercase
        s = s.lower()
        # Replace hyphens with spaces before removing special chars
        s = s.replace('-', ' ')
        # Remove special characters, keep alphanumeric and spaces
        s = re.sub(r'[^\w\s]', '', s)
        # Collapse multiple spaces
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    def strings_match(self, str1, str2, threshold=0.7):
        """Check if two strings match with fuzzy matching"""
        norm1 = self.normalize_string(str1)
        norm2 = self.normalize_string(str2)

        # Exact match after normalization
        if norm1 == norm2:
            return True

        # Check if one contains the other
        if norm1 in norm2 or norm2 in norm1:
            return True

        # Check word overlap
        words1 = set(norm1.split())
        words2 = set(norm2.split())

        if not words1 or not words2:
            return False

        # Calculate overlap percentage
        overlap = len(words1 & words2)
        total = min(len(words1), len(words2))

        return (overlap / total) >= threshold if total > 0 else False

    def search_itunes_for_album(self, album_name, artist_name, release_date=None):
        """Search iTunes API for direct Apple Music album link with validation"""
        try:
            # Get primary artist (first one before comma)
            primary_artist = artist_name.split(',')[0].strip()

            # Try multiple search strategies
            search_attempts = [
                # Strategy 1: Full album + primary artist
                f"{album_name} {primary_artist}",
                # Strategy 2: Just album name
                f"{album_name}",
                # Strategy 3: Album + all artists
                f"{album_name} {artist_name}"
            ]

            url = "https://itunes.apple.com/search"
            best_match = None
            best_match_score = 0

            for attempt_num, search_query in enumerate(search_attempts, 1):
                params = {
                    'term': search_query,
                    'entity': 'album',
                    'limit': 5,  # Get top 5 to find best match
                    'country': 'US'
                }

                response = requests.get(url, params=params, timeout=5)
                response.raise_for_status()
                data = response.json()

                # Check if we got results
                if data.get('resultCount', 0) > 0:
                    # Try to find the best match from results
                    for result in data['results']:
                        result_album = result.get('collectionName', '')
                        result_artist = result.get('artistName', '')
                        result_type = result.get('collectionType', '')
                        result_track_count = result.get('trackCount', 0)
                        result_release = result.get('releaseDate', '')[:10]  # YYYY-MM-DD

                        # Skip if it's not an album/EP/single collection
                        if result_type not in ['Album', 'EP', 'Single', '']:
                            continue

                        # Skip if track count is 0 (invalid result)
                        if result_track_count == 0:
                            continue

                        # Validate album name match
                        album_matches = self.strings_match(album_name, result_album)
                        # Validate artist match (check if any of our artists match)
                        artist_list = [a.strip() for a in artist_name.split(',')]
                        artist_matches = any(
                            self.strings_match(a, result_artist)
                            for a in artist_list
                        )

                        if album_matches and artist_matches:
                            # Calculate match score (higher is better)
                            score = 0

                            # Perfect album name match = +100
                            if self.normalize_string(album_name) == self.normalize_string(result_album):
                                score += 100
                            elif album_matches:
                                score += 50

                            # Perfect artist match = +100
                            if any(self.normalize_string(a) == self.normalize_string(result_artist) for a in artist_list):
                                score += 100
                            elif artist_matches:
                                score += 50

                            # Release date proximity = +50
                            if release_date and result_release:
                                if release_date == result_release:
                                    score += 50
                                elif abs((datetime.strptime(release_date, '%Y-%m-%d') -
                                         datetime.strptime(result_release, '%Y-%m-%d')).days) <= 7:
                                    score += 25

                            apple_music_url = result.get('collectionViewUrl', None)
                            if apple_music_url and score > best_match_score:
                                best_match = {
                                    'url': apple_music_url,
                                    'album': result_album,
                                    'artist': result_artist,
                                    'type': result_type,
                                    'tracks': result_track_count,
                                    'release': result_release,
                                    'score': score,
                                    'attempt': attempt_num
                                }
                                best_match_score = score

                    # If we found a match in this attempt and it's very good, return it
                    if best_match and best_match_score >= 100:  # Lowered threshold for better matching
                        print(f"   ✅ iTunes match (attempt {best_match['attempt']}, score {best_match_score}): {best_match['album']} - {best_match['artist']} [{best_match['type']}, {best_match['tracks']} tracks]")
                        time.sleep(0.2)
                        return best_match['url']

                    # If no strong match, continue to next strategy
                    print(f"   ⚠️  No strong match in attempt {attempt_num} (best score: {best_match_score}) for: {album_name}")

                time.sleep(0.2)

            # Return best match if we found any reasonable match at all
            if best_match and best_match_score >= 75:  # Accept even partial matches
                print(f"   ✅ iTunes best match (score {best_match_score}): {best_match['album']} - {best_match['artist']} [{best_match['type']}]")
                return best_match['url']

            # All strategies failed or score too low
            if best_match:
                print(f"   ❌ Best match score too low ({best_match_score}) for: {album_name} -> {best_match['album']}")
            else:
                print(f"   ❌ No iTunes match found after {len(search_attempts)} attempts for: {album_name}")
            return None

        except Exception as e:
            print(f"   ⚠️  iTunes API error for '{album_name}': {e}")
            time.sleep(0.2)
            return None

    def clean_for_apple_music_search(self, text):
        """Clean text specifically for Apple Music search queries"""
        import re

        # Remove featured artist notation - Apple Music doesn't need it
        text = re.sub(r'\(feat\..*?\)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[feat\..*?\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'feat\..*$', '', text, flags=re.IGNORECASE)
        text = re.sub(r'featuring.*$', '', text, flags=re.IGNORECASE)

        # Remove volume/vol notation (too specific for search)
        text = re.sub(r',?\s*vol\.?\s*\d+', '', text, flags=re.IGNORECASE)
        text = re.sub(r',?\s*volume\s*\d+', '', text, flags=re.IGNORECASE)

        # Remove pt/part notation for singles (not helpful in search)
        text = re.sub(r',?\s*pt\.?\s*\d+', '', text, flags=re.IGNORECASE)
        text = re.sub(r',?\s*part\s*\d+', '', text, flags=re.IGNORECASE)

        # Remove edition markers that make search too specific
        text = re.sub(r'\(.*?edition\)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[.*?edition\]', '', text, flags=re.IGNORECASE)
        # Remove common edition suffixes: "Deluxe Edition", "Black Heart Edition", etc.
        text = re.sub(r'\s+(deluxe|expanded|special|limited|ultimate|extended|remaster|black\s+heart|errtime)\s+edition$', '', text, flags=re.IGNORECASE)

        # Remove remix indicators (keep them simple)
        text = re.sub(r'\s*-\s*.*?remix$', ' Remix', text, flags=re.IGNORECASE)

        # Remove trailing commas and clean up punctuation
        text = re.sub(r',\s*$', '', text)

        # Clean up extra spaces
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    def get_album_details(self, album):
        """Extract relevant album details with iTunes API for direct Apple Music links"""
        artists = ", ".join([artist['name'] for artist in album['artists']])
        release_date = album.get('release_date', '')

        apple_music_url = None

        # ALWAYS try iTunes API first for all releases
        apple_music_url = self.search_itunes_for_album(
            album['name'],
            artists,
            release_date=release_date
        )

        if apple_music_url:
            print(f"   ✅ Got direct iTunes link for: {album['name']}")

        # Fallback to optimized search URL only if iTunes API fails
        if not apple_music_url:
            # Get primary artist for cleaner search
            primary_artist = artists.split(',')[0].strip()

            # Clean the album name (remove feat., Vol., pt., etc.)
            clean_album_name = self.clean_for_apple_music_search(album['name'])

            # For new releases, keep search simple: just clean album name + artist
            # Apple Music search works best with simple, broad terms
            search_term = f"{clean_album_name} {primary_artist}"

            apple_music_url = f"https://music.apple.com/us/search?term={quote(search_term)}"
            print(f"   ⚠️  Using search URL fallback for: {album['name']}")

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
        """Fetch music news from various RSS feeds including Reddit and YouTube"""
        news_sources = [
            # General Music News
            {
                'name': 'Pitchfork',
                'url': 'https://pitchfork.com/rss/news/',
                'category': 'general'
            },
            {
                'name': 'Consequence',
                'url': 'https://consequence.net/feed/',
                'category': 'general'
            },
            {
                'name': 'Rolling Stone',
                'url': 'https://www.rollingstone.com/music/music-news/feed/',
                'category': 'general'
            },
            {
                'name': 'NME',
                'url': 'https://www.nme.com/news/music/feed',
                'category': 'general'
            },
            {
                'name': 'Billboard',
                'url': 'https://www.billboard.com/feed/',
                'category': 'general'
            },
            {
                'name': 'Brooklyn Vegan',
                'url': 'https://www.brooklynvegan.com/rss',
                'category': 'general'
            },

            # Hip Hop Sources
            {
                'name': 'HipHopDX',
                'url': 'https://hiphopdx.com/feed',
                'category': 'hiphop'
            },
            {
                'name': 'Complex Music',
                'url': 'https://www.complex.com/music/rss',
                'category': 'hiphop'
            },
            {
                'name': 'The FADER',
                'url': 'https://www.thefader.com/feed',
                'category': 'hiphop'
            },
            {
                'name': 'HotNewHipHop',
                'url': 'https://www.hotnewhiphop.com/rss',
                'category': 'hiphop'
            },
            {
                'name': 'XXL Mag',
                'url': 'https://www.xxlmag.com/feed/',
                'category': 'hiphop'
            },
            {
                'name': 'Rap-Up',
                'url': 'https://www.rap-up.com/feed/',
                'category': 'hiphop'
            },
            {
                'name': 'Reddit r/hiphopheads',
                'url': 'https://www.reddit.com/r/hiphopheads/.rss',
                'category': 'hiphop',
                'is_reddit': True,
                'min_upvotes': 25  # Only show posts with 25+ upvotes
            },

            # Rock/Alternative Sources
            {
                'name': 'Stereogum',
                'url': 'https://www.stereogum.com/feed/',
                'category': 'rock'
            },
            {
                'name': 'Alternative Press',
                'url': 'https://www.altpress.com/feed/',
                'category': 'rock'
            },
            {
                'name': 'Loudwire',
                'url': 'https://loudwire.com/feed/',
                'category': 'rock'
            },

            # YouTube - The Needle Drop
            {
                'name': 'The Needle Drop',
                'url': 'https://www.youtube.com/feeds/videos.xml?channel_id=UCt7fwAhXDy3oNFTAzF2o8Pw',
                'category': 'general',
                'is_youtube': True
            }
        ]

        all_news = []

        print("📰 Fetching music news from RSS feeds...")
        for source in news_sources:
            try:
                feed = feedparser.parse(source['url'])

                # Get more articles per source (15 instead of 5)
                for entry in feed.entries[:15]:
                    # Handle Reddit posts with upvote filtering
                    if source.get('is_reddit'):
                        # Extract upvotes from Reddit RSS (it's in the title like "[FRESH] Title (123 points)")
                        import re
                        title = entry.title

                        # Try to extract upvotes from content or title
                        upvotes = None
                        content = entry.get('content', [{}])[0].get('value', '') if entry.get('content') else ''

                        # Look for upvote count in content
                        upvote_match = re.search(r'(\d+)\s+points?', content)
                        if upvote_match:
                            upvotes = int(upvote_match.group(1))

                        # Also try to find in summary
                        if not upvotes:
                            summary = entry.get('summary', '')
                            upvote_match = re.search(r'(\d+)\s+points?', summary)
                            if upvote_match:
                                upvotes = int(upvote_match.group(1))

                        # Skip if below minimum upvotes (only if we found upvotes)
                        min_upvotes = source.get('min_upvotes', 0)
                        if upvotes is not None and upvotes < min_upvotes:
                            continue

                        # Clean up Reddit title (remove subreddit prefix)
                        title = re.sub(r'^\[.*?\]\s*', '', title)

                        # Add upvote count to title if available
                        if upvotes is not None:
                            title = f"{title} ({upvotes} upvotes)"

                    # Handle YouTube videos
                    elif source.get('is_youtube'):
                        title = entry.title
                        # YouTube RSS includes "published" field
                    else:
                        title = entry.title

                    pub_date = entry.get('published_parsed') or entry.get('updated_parsed')
                    if pub_date:
                        pub_date = datetime(*pub_date[:6])
                    else:
                        pub_date = datetime.now()

                    # Increased to 7 days for more results
                    if datetime.now() - pub_date <= timedelta(days=7):
                        summary = entry.get('summary', '')

                        # Clean up summary (remove HTML tags if present)
                        import re
                        summary = re.sub(r'<[^>]+>', '', summary)
                        summary = summary[:200] + '...' if len(summary) > 200 else summary
                        if not summary:
                            summary = 'Click to read more.'

                        all_news.append({
                            'title': title,
                            'link': entry.link,
                            'source': source['name'],
                            'category': source['category'],
                            'published': pub_date.strftime('%Y-%m-%d %H:%M'),
                            'summary': summary
                        })

                time.sleep(0.5)
            except Exception as e:
                print(f"❌ Error fetching from {source['name']}: {e}")
                continue

        all_news.sort(key=lambda x: x['published'], reverse=True)
        print(f"✅ Found {len(all_news[:50])} news articles from {len(news_sources)} sources")
        return all_news[:50]  # Return top 50 articles instead of 20

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
        print("Fetching Hip Hop releases from artist database...")
        print("-"*60)
        # Use curated artist database for hip-hop
        hiphop_albums = fetcher.get_releases_from_artist_database('hiphop', min_popularity=0)
        hiphop_data = [fetcher.get_album_details(album) for album in hiphop_albums]

        print("\n" + "-"*60)
        print("Fetching Alternative releases from artist database...")
        print("-"*60)
        # Use curated artist database for alternative
        rock_albums = fetcher.get_releases_from_artist_database('alternative', min_popularity=0)
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
