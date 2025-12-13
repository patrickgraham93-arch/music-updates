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
            print("Warning: Spotify credentials not found. Using demo data.")
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
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            self.spotify_token = response.json()['access_token']
            return self.spotify_token
        except Exception as e:
            print(f"Error getting Spotify token: {e}")
            return None
    
    def search_new_releases(self, genre, limit=20):
        """Search for new releases in a specific genre"""
        if not self.spotify_token:
            return []
        
        today = datetime.now()
        week_ago = today - timedelta(days=7)
        
        headers = {"Authorization": f"Bearer {self.spotify_token}"}
        
        search_query = f"genre:{genre} year:{today.year}"
        url = f"https://api.spotify.com/v1/search?q={search_query}&type=album&limit={limit}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            albums = response.json()['albums']['items']
            
            recent_albums = []
            for album in albums:
                release_date = album['release_date']
                try:
                    if len(release_date) == 4:
                        album_date = datetime(int(release_date), 1, 1)
                    elif len(release_date) == 7:
                        album_date = datetime.strptime(release_date, "%Y-%m")
                    else:
                        album_date = datetime.strptime(release_date, "%Y-%m-%d")
                    
                    if album_date >= week_ago:
                        recent_albums.append(album)
                except:
                    continue
            
            return recent_albums[:10]
        except Exception as e:
            print(f"Error searching releases for {genre}: {e}")
            return []
    
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
        
        for source in news_sources:
            try:
                feed = feedparser.parse(source['url'])
                for entry in feed.entries[:5]:
                    pub_date = entry.get('published_parsed') or entry.get('updated_parsed')
                    if pub_date:
                        pub_date = datetime(*pub_date[:6])
                    else:
                        pub_date = datetime.now()
                    
                    if datetime.now() - pub_date <= timedelta(days=1):
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
                print(f"Error fetching from {source['name']}: {e}")
                continue
        
        all_news.sort(key=lambda x: x['published'], reverse=True)
        return all_news[:20]
    
    def generate_demo_data(self):
        """Generate demo data when API credentials aren't available"""
        return {
            'hiphop': [
                {
                    'name': 'Demo Album',
                    'artists': 'Demo Artist',
                    'release_date': datetime.now().strftime('%Y-%m-%d'),
                    'image': 'https://via.placeholder.com/300',
                    'spotify_url': '#',
                    'apple_music_url': '#',
                    'total_tracks': 12,
                    'album_type': 'album'
                }
            ],
            'rock': [],
            'news': [
                {
                    'title': 'Demo News Article',
                    'link': '#',
                    'source': 'Demo Source',
                    'category': 'general',
                    'published': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'summary': 'This is demo data. Add your Spotify API credentials to see real music data.'
                }
            ],
            'last_updated': datetime.now().isoformat()
        }

def main():
    fetcher = MusicDataFetcher()
    
    token = fetcher.get_spotify_token()
    
    if token:
        print("Fetching hip hop releases...")
        hiphop_albums = fetcher.search_new_releases('hip-hop')
        hiphop_data = [fetcher.get_album_details(album) for album in hiphop_albums]
        
        print("Fetching alternative rock releases...")
        rock_albums = fetcher.search_new_releases('alternative')
        rock_data = [fetcher.get_album_details(album) for album in rock_albums]
        
        print("Fetching music news...")
        news_data = fetcher.fetch_music_news()
        
        data = {
            'hiphop': hiphop_data,
            'rock': rock_data,
            'news': news_data,
            'last_updated': datetime.now().isoformat()
        }
    else:
        print("Using demo data...")
        data = fetcher.generate_demo_data()
    
    with open('music_data.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Data saved! Found {len(data['hiphop'])} hip hop releases, {len(data['rock'])} rock releases, and {len(data['news'])} news articles.")

if __name__ == "__main__":
    main()
