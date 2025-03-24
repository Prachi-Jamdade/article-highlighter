import requests
import xml.etree.ElementTree as ET
import sys
import json
import re
from github import Github
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class ArticleSource(ABC):
    """Abstract base class for different article sources"""

    @abstractmethod
    def fetch_articles(self) -> List[Dict[str, Any]]:
        """Fetch articles from the source"""
        pass


class RSSFeedSource(ArticleSource):
    """Article source that fetches from RSS feeds"""

    def __init__(self, feed_url: str):
        self.feed_url = feed_url

    def fetch_articles(self) -> List[Dict[str, Any]]:
        """Fetch articles from RSS feed"""
        feed_content = self._fetch_feed_content()
        return self._parse_feed_content(feed_content)

    def _fetch_feed_content(self) -> bytes:
        """Fetch the raw RSS feed content"""
        response = requests.get(self.feed_url)
        response.raise_for_status()
        return response.content

    def _parse_feed_content(self, feed_content: bytes) -> List[Dict[str, Any]]:
        """Parse RSS feed content into article data"""
        root = ET.fromstring(feed_content)
        articles = []
        for item in root.findall('./channel/item'):
            title = item.find('title').text
            link = item.find('link').text
            articles.append({'title': title, 'link': link})
        return articles


class DevToSource(ArticleSource):
    """Article source that fetches from Dev.to"""

    def __init__(self, username: str):
        self.username = username

    def fetch_articles(self) -> List[Dict[str, Any]]:
        """Fetch articles from Dev.to API"""
        api_url = f"https://dev.to/api/articles?username={self.username}"
        response = requests.get(api_url)
        response.raise_for_status()
        articles = response.json()
        return [
            {
                'title': article['title'],
                'link': article['url'],
                'positive_reactions_count': article['positive_reactions_count'],
                'comments_count': article['comments_count']
            }
            for article in articles
        ]

    @staticmethod
    def extract_username_from_url(profile_url: str) -> Optional[str]:
        """Extract Dev.to username from profile URL"""
        match = re.search(r'dev\.to\/@?([\w\d]+)', profile_url)
        if match:
            return match.group(1)
        return None


class ArticleFilter:
    """Filter and sort articles based on criteria"""

    @staticmethod
    def get_top_articles(articles, top_n: int = 5) -> List[Dict[str, Any]]:
        """Get top articles based on reactions and comments"""
        sorted_articles = sorted(
            articles,
            key=lambda x: (x.get('positive_reactions_count', 0), x.get('comments_count', 0)),
            reverse=True
        )
        return sorted_articles[:top_n]

    @staticmethod
    def limit_articles(articles: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        """Limit the number of articles"""
        return articles[:limit]


class ArticleWriter:
    """Write articles to file"""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def write_articles(self, articles: List[Dict[str, Any]]) -> None:
        """Write articles to markdown file"""
        with open(self.file_path, 'w') as f:
            f.write('## Articles\n\n')
            for article in articles:
                f.write(f"- [{article['title']}]({article['link']})\n")


class ReadmeUpdater:
    """Update README with articles"""

    def __init__(self, repo, articles_file_path: str):
        self.repo = repo
        self.articles_file_path = articles_file_path

    def update(self) -> None:
        """Update README with articles content"""
        readme = self.repo.get_readme()
        readme_content = readme.decoded_content.decode()

        start_marker = '<!-- ARTICLES -->'
        end_marker = '<!-- /ARTICLES -->'

        start_idx = readme_content.find(start_marker) + len(start_marker)
        end_idx = readme_content.find(end_marker)

        if start_idx == -1 or end_idx == -1:
            raise ValueError("Markers not found in README file")

        with open(self.articles_file_path, 'r') as ra:
            recent_articles = ra.read()

        updated_content = (readme_content[:start_idx].strip() + "\n\n" +
                          recent_articles.strip() + "\n" +
                          readme_content[end_idx:].strip())

        self.repo.update_file(readme.path, 'Update articles', updated_content, readme.sha)


class SourceFactory:
    """Factory for creating article sources"""

    @staticmethod
    def create_source(url: str) -> Optional[ArticleSource]:
        """Create appropriate article source based on URL"""
        if 'dev.to' in url:
            username = DevToSource.extract_username_from_url(url)
            if username:
                return DevToSource(username)
        else:
            return RSSFeedSource(url)
        return None


def main(feed_urls: List[str], article_limit: int, article_type: str, github_token: str, articles_md_path: str) -> None:
    """Main function to orchestrate the article fetching and README update process"""
    # Create article sources
    sources = [SourceFactory.create_source(url) for url in feed_urls]
    sources = [source for source in sources if source is not None]

    # Fetch articles from all sources
    all_articles = []
    for source in sources:
        articles = source.fetch_articles()

        # Apply filtering based on article type
        if article_type == 'top' and article_limit > 0 and isinstance(source, DevToSource):
            articles = ArticleFilter.get_top_articles(articles, article_limit)

        all_articles.extend(articles)

    # Limit the total number of articles
    all_articles = ArticleFilter.limit_articles(all_articles, article_limit)

    # Write articles to file
    writer = ArticleWriter(articles_md_path)
    writer.write_articles(all_articles)

    # Update README
    g = Github(github_token)
    user = g.get_user()
    repo = user.get_repo(user.login)
    updater = ReadmeUpdater(repo, articles_md_path)
    updater.update()


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python update_articles.py <feed_urls> <article_limit> <article_type> <github_token>")
        sys.exit(1)

    FEED_URLS = sys.argv[1].split(',')
    ARTICLE_LIMIT = int(sys.argv[2])
    ARTICLE_TYPE = sys.argv[3]
    GITHUB_TOKEN = sys.argv[4]
    ARTICLES_MD_PATH = 'articles.md'

    main(FEED_URLS, ARTICLE_LIMIT, ARTICLE_TYPE, GITHUB_TOKEN, ARTICLES_MD_PATH)
