from typing import List, Dict, Optional
from datetime import datetime, timedelta
from collections import Counter
import numpy as np
from ..models.models import UserProfile, Suggestion, SessionContext

class PersonalizationService:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.session_timeout = timedelta(minutes=30)
        
    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """Get or create user profile"""
        # Try to get from cache
        profile_data = await self.redis.get(f"user_profile:{user_id}")
        
        if profile_data:
            return UserProfile(**profile_data)
        
        # Create new profile
        profile = UserProfile(
            user_id=user_id,
            role="guest",
            recent_searches=[],
            click_history={},
            domain_preferences={},
            location_history=[],
            search_time_patterns={}
        )
        
        await self._save_user_profile(profile)
        return profile
    
    async def update_user_profile(self, user_id: str, search_query: str, 
                                  clicked_suggestion: Optional[str] = None):
        """Update user profile based on search behavior"""
        profile = await self.get_user_profile(user_id)
        
        # Update recent searches
        profile.recent_searches.insert(0, search_query)
        profile.recent_searches = profile.recent_searches[:20]  # Keep last 20
        
        # Update click history
        if clicked_suggestion:
            profile.click_history[clicked_suggestion] = \
                profile.click_history.get(clicked_suggestion, 0) + 1
        
        # Update search time patterns
        current_hour = datetime.now().hour
        profile.search_time_patterns[current_hour] = \
            profile.search_time_patterns.get(current_hour, 0) + 1
        
        # Update domain preferences based on clicks
        self._update_domain_preferences(profile)
        
        await self._save_user_profile(profile)
    
    def _update_domain_preferences(self, profile: UserProfile):
        """Update domain preferences based on click history"""
        if not profile.click_history:
            return
        
        # This would use a classifier in production
        # Simple keyword-based categorization
        category_keywords = {
            'technology': ['python', 'java', 'javascript', 'coding', 'software'],
            'food': ['restaurant', 'recipe', 'pizza', 'dinner'],
            'shopping': ['amazon', 'walmart', 'buy', 'price'],
            'entertainment': ['movie', 'netflix', 'youtube', 'music']
        }
        
        category_counts = Counter()
        
        for query, clicks in profile.click_history.items():
            for category, keywords in category_keywords.items():
                if any(keyword in query.lower() for keyword in keywords):
                    category_counts[category] += clicks
        
        total_clicks = sum(category_counts.values())
        if total_clicks > 0:
            profile.domain_preferences = {
                cat: count / total_clicks 
                for cat, count in category_counts.items()
            }
    
    async def create_session(self, user_id: str, session_id: str) -> SessionContext:
        """Create a new search session"""
        session = SessionContext(
            session_id=session_id,
            user_id=user_id,
            queries=[],
            start_time=datetime.now(),
            last_activity=datetime.now(),
            clicked_suggestions=[]
        )
        
        await self._save_session(session)
        return session
    
    async def update_session(self, session_id: str, query: str, 
                            clicked: Optional[str] = None):
        """Update session with new query or click"""
        session = await self.get_session(session_id)
        if not session:
            return
        
        session.queries.append(query)
        session.last_activity = datetime.now()
        
        if clicked:
            session.clicked_suggestions.append(clicked)
        
        await self._save_session(session)
    
    async def get_session(self, session_id: str) -> Optional[SessionContext]:
        """Get session by ID"""
        session_data = await self.redis.get(f"session:{session_id}")
        if session_data:
            session = SessionContext(**session_data)
            # Check if session expired
            if datetime.now() - session.last_activity > self.session_timeout:
                await self.redis.delete(f"session:{session_id}")
                return None
            return session
        return None
    
    async def _save_user_profile(self, profile: UserProfile):
        """Save user profile to Redis"""
        await self.redis.setex(
            f"user_profile:{profile.user_id}",
            86400,  # 24 hours TTL
            profile.__dict__
        )
    
    async def _save_session(self, session: SessionContext):
        """Save session to Redis"""
        await self.redis.setex(
            f"session:{session.session_id}",
            1800,  # 30 minutes TTL
            session.__dict__
        )
    
    def get_personalized_ranking(self, suggestions: List[Suggestion], 
                                 user_profile: UserProfile,
                                 session: SessionContext) -> List[Suggestion]:
        """Apply personalization to suggestion ranking"""
        
        for suggestion in suggestions:
            # Apply personalization boost
            suggestion.score *= user_profile.get_personalization_boost(suggestion)
            
            # Apply session-based boost
            if session and session.queries:
                # Boost if suggestion relates to previous queries
                for prev_query in session.queries[-3:]:  # Look at last 3 queries
                    if self._are_queries_related(prev_query, suggestion.text):
                        suggestion.score *= 1.2
                        break
            
            # Boost if suggestion was clicked before in this session
            if suggestion.text in session.clicked_suggestions:
                suggestion.score *= 1.5
        
        # Re-sort by updated scores
        suggestions.sort(key=lambda x: x.score, reverse=True)
        return suggestions
    
    def _are_queries_related(self, query1: str, query2: str) -> bool:
        """Check if two queries are semantically related"""
        # Simplified version - would use embeddings in production
        query1_words = set(query1.lower().split())
        query2_words = set(query2.lower().split())
        
        # Check for word overlap
        if query1_words & query2_words:
            return True
        
        # Check for common patterns
        common_relations = [
            ('python', 'django'),
            ('java', 'spring'),
            ('javascript', 'react'),
            ('machine learning', 'ai'),
            ('restaurant', 'food'),
        ]
        
        for w1, w2 in common_relations:
            if (w1 in query1.lower() and w2 in query2.lower()) or \
               (w2 in query1.lower() and w1 in query2.lower()):
                return True
        
        return False