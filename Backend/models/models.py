from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional, Set
from enum import Enum

class UserRole(Enum):
    GUEST = "guest"
    REGULAR = "regular"
    PREMIUM = "premium"
    ADMIN = "admin"

@dataclass
class SearchQuery:
    query_id: str
    text: str
    user_id: str
    timestamp: datetime
    location: Optional[Dict[str, float]] = None  # {"lat": 40.7128, "lon": -74.0060}
    category: Optional[str] = None
    clicked_results: List[str] = None

@dataclass
class Suggestion:
    id: str
    text: str
    category: str
    frequency: int = 0
    click_count: int = 0
    last_updated: datetime = None
    trending_score: float = 0.0
    related_queries: List[str] = None
    
    def get_ctr(self) -> float:
        """Calculate click-through rate"""
        if self.frequency == 0:
            return 0
        return self.click_count / self.frequency
    
    def get_recency_factor(self, current_time: datetime, half_life_hours: int = 24) -> float:
        """Calculate recency factor using exponential decay"""
        if not self.last_updated:
            return 0.5
        
        hours_diff = (current_time - self.last_updated).total_seconds() / 3600
        decay = 2 ** (-hours_diff / half_life_hours)
        return max(0.1, min(1.0, decay))

@dataclass
class UserProfile:
    user_id: str
    role: UserRole
    recent_searches: List[str]  # Last N searches
    click_history: Dict[str, int]  # query -> click_count
    domain_preferences: Dict[str, float]  # category -> preference_score
    location_history: List[Dict[str, float]]
    search_time_patterns: Dict[int, int]  # hour_of_day -> search_count
    
    def get_personalization_boost(self, suggestion: Suggestion) -> float:
        """Calculate personalization boost for a suggestion"""
        boost = 1.0
        
        # Boost if user has searched similar before
        if suggestion.text in self.recent_searches:
            boost *= 1.5
        
        # Boost based on category preference
        category_boost = self.domain_preferences.get(suggestion.category, 1.0)
        boost *= category_boost
        
        return boost

@dataclass
class SessionContext:
    session_id: str
    user_id: str
    queries: List[str]
    start_time: datetime
    last_activity: datetime
    clicked_suggestions: List[str]