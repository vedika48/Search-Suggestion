from typing import Dict, List, Optional, Tuple
from datetime import datetime
import heapq
from collections import defaultdict
from Backend.models.models import Suggestion, UserProfile, SessionContext

class TrieNode:
    __slots__ = ['children', 'is_end', 'suggestion_ids', 'frequency_sum']
    
    def __init__(self):
        self.children: Dict[str, 'TrieNode'] = {}
        self.is_end: bool = False
        self.suggestion_ids: List[str] = []  # IDs of suggestions at this node
        self.frequency_sum: int = 0  # Sum of frequencies for prefix optimization

class AdvancedTrie:
    def __init__(self):
        self.root = TrieNode()
        self.suggestions: Dict[str, Suggestion] = {}  # suggestion_id -> Suggestion
        self.prefix_cache: Dict[str, List[Tuple[float, str]]] = {}  # prefix -> [(score, id)]
        self.CACHE_TTL = 300  # 5 minutes
        self.cache_timestamps: Dict[str, datetime] = {}
        
    def insert(self, suggestion: Suggestion):
        """Insert a suggestion with metadata"""
        self.suggestions[suggestion.id] = suggestion
        node = self.root
        
        for char in suggestion.text.lower():
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
            node.suggestion_ids.append(suggestion.id)
            node.frequency_sum += suggestion.frequency
        
        node.is_end = True
        # Invalidate cache for relevant prefixes
        self._invalidate_prefix_cache(suggestion.text)
    
    def search_with_typo_tolerance(self, prefix: str, max_edits: int = 2, 
                                   top_k: int = 10) -> List[Tuple[float, Suggestion]]:
        """Search with typo tolerance using Levenshtein distance"""
        candidates = []
        
        def dfs(node: TrieNode, current_word: str, edits_remaining: int):
            if edits_remaining < 0:
                return
            
            # If we have valid suggestions at this node, add them
            if node.is_end and current_word in self.suggestions:
                distance = self._levenshtein_distance(prefix, current_word)
                if distance <= max_edits:
                    candidates.append((distance, current_word))
            
            # Continue DFS
            for char, child_node in node.children.items():
                dfs(child_node, current_word + char, edits_remaining - 1)
        
        # Start DFS from root
        dfs(self.root, "", max_edits)
        
        # Sort by edit distance and then by frequency
        candidates.sort(key=lambda x: (x[0], -self.suggestions[x[1]].frequency))
        
        # Return top K suggestions
        return [(1.0 / (c[0] + 1), self.suggestions[c[1]]) for c in candidates[:top_k]]
    
    def get_suggestions_with_score(self, prefix: str, user_profile: Optional[UserProfile] = None,
                                   session: Optional[SessionContext] = None,
                                   context: Optional[Dict] = None) -> List[Suggestion]:
        """Get ranked suggestions with all advanced features"""
        
        # Check cache
        cache_key = f"{prefix}_{user_profile.user_id if user_profile else 'guest'}"
        if self._is_cache_valid(cache_key):
            return [self.suggestions[sid] for _, sid in self.prefix_cache[cache_key]]
        
        # Find prefix node
        node = self._find_prefix_node(prefix)
        if not node:
            # Try typo tolerance if no exact matches
            scored_suggestions = self.search_with_typo_tolerance(prefix)
            return [s for _, s in scored_suggestions[:10]]
        
        # Get all suggestion IDs under this prefix
        candidate_ids = self._collect_suggestions(node)
        
        # Score and rank suggestions
        ranked_suggestions = self._rank_suggestions(
            candidate_ids, 
            prefix, 
            user_profile,
            session,
            context
        )
        
        # Cache results
        self.prefix_cache[cache_key] = [(s.score, s.id) for s in ranked_suggestions[:20]]
        self.cache_timestamps[cache_key] = datetime.now()
        
        return ranked_suggestions[:10]
    
    def _rank_suggestions(self, suggestion_ids: List[str], prefix: str,
                         user_profile: Optional[UserProfile],
                         session: Optional[SessionContext],
                         context: Optional[Dict]) -> List[Suggestion]:
        """Advanced ranking with multiple factors"""
        
        scored_suggestions = []
        current_time = datetime.now()
        
        for sid in suggestion_ids:
            suggestion = self.suggestions[sid]
            
            # Base score components
            prefix_match_score = self._calculate_prefix_match_score(suggestion.text, prefix)
            popularity_score = self._calculate_popularity_score(suggestion)
            recency_score = suggestion.get_recency_factor(current_time)
            trending_score = suggestion.trending_score
            
            # Contextual boosts
            context_boost = self._calculate_context_boost(suggestion, context)
            
            # Personalization
            personalization_boost = 1.0
            if user_profile:
                personalization_boost = user_profile.get_personalization_boost(suggestion)
            
            # Session-based boost
            session_boost = 1.0
            if session and session.queries:
                session_boost = self._calculate_session_boost(suggestion, session)
            
            # Final weighted score
            final_score = (
                0.3 * prefix_match_score +
                0.25 * popularity_score +
                0.15 * recency_score +
                0.1 * trending_score +
                0.1 * context_boost +
                0.1 * personalization_boost * session_boost
            )
            
            suggestion.score = final_score
            scored_suggestions.append(suggestion)
        
        # Sort by final score
        scored_suggestions.sort(key=lambda x: x.score, reverse=True)
        return scored_suggestions
    
    def _calculate_prefix_match_score(self, text: str, prefix: str) -> float:
        """Calculate how well the suggestion matches the prefix"""
        if text.lower().startswith(prefix.lower()):
            return 1.0
        # Use Levenshtein for partial matches
        distance = self._levenshtein_distance(text[:len(prefix)], prefix)
        return 1.0 / (distance + 1)
    
    def _calculate_popularity_score(self, suggestion: Suggestion) -> float:
        """Calculate popularity score based on frequency and CTR"""
        if suggestion.frequency == 0:
            return 0.0
        
        # Normalize frequency (log scale)
        freq_score = min(1.0, suggestion.frequency / 10000)  # Cap at 10k searches
        
        # CTR score
        ctr_score = suggestion.get_ctr()
        
        return 0.6 * freq_score + 0.4 * ctr_score
    
    def _calculate_context_boost(self, suggestion: Suggestion, context: Dict) -> float:
        """Apply contextual boosts (time, location, category)"""
        if not context:
            return 1.0
        
        boost = 1.0
        
        # Time-based boost
        if 'time_of_day' in context:
            hour = context['time_of_day']
            # Boost food-related queries during meal times
            if suggestion.category == 'restaurant':
                if 7 <= hour <= 9:  # Breakfast
                    boost *= 1.3
                elif 12 <= hour <= 14:  # Lunch
                    boost *= 1.5
                elif 18 <= hour <= 21:  # Dinner
                    boost *= 1.5
        
        # Location-based boost
        if 'location' in context and hasattr(suggestion, 'location_score'):
            boost *= suggestion.location_score.get(context['location'], 1.0)
        
        return boost
    
    def _calculate_session_boost(self, suggestion: Suggestion, session: SessionContext) -> float:
        """Boost suggestions related to session context"""
        if not session.queries:
            return 1.0
        
        last_query = session.queries[-1]
        
        # Check if suggestion is related to last query
        if suggestion.text in session.clicked_suggestions:
            return 1.3
        
        # Check semantic similarity (simplified - would use embeddings in production)
        if last_query.lower() in suggestion.text.lower() or suggestion.text.lower() in last_query.lower():
            return 1.2
        
        return 1.0
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def _find_prefix_node(self, prefix: str) -> Optional[TrieNode]:
        """Find node corresponding to prefix"""
        node = self.root
        for char in prefix.lower():
            if char not in node.children:
                return None
            node = node.children[char]
        return node
    
    def _collect_suggestions(self, node: TrieNode) -> List[str]:
        """Collect all suggestion IDs under a node"""
        suggestions = []
        
        def dfs(current_node: TrieNode):
            if current_node.is_end:
                suggestions.extend(current_node.suggestion_ids)
            for child in current_node.children.values():
                dfs(child)
        
        dfs(node)
        return suggestions
    
    def _invalidate_prefix_cache(self, text: str):
        """Invalidate cache for all prefixes of a word"""
        for i in range(1, len(text) + 1):
            prefix = text[:i]
            keys_to_remove = [k for k in self.prefix_cache.keys() if k.startswith(prefix)]
            for key in keys_to_remove:
                self.prefix_cache.pop(key, None)
                self.cache_timestamps.pop(key, None)
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid"""
        if cache_key not in self.prefix_cache:
            return False
        
        timestamp = self.cache_timestamps.get(cache_key)
        if not timestamp:
            return False
        
        age = (datetime.now() - timestamp).total_seconds()
        return age < self.CACHE_TTL