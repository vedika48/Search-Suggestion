from typing import List, Tuple, Dict, Set
from Levenshtein import distance as lev_distance
import re
from collections import defaultdict

class KeyboardLayout:
    """Simulates keyboard adjacency for typo correction"""
    
    # QWERTY keyboard adjacency
    QWERTY_ADJACENT = {
        'q': ['w', 'a', 's'],
        'w': ['q', 'e', 'a', 's', 'd'],
        'e': ['w', 'r', 's', 'd', 'f'],
        'r': ['e', 't', 'd', 'f', 'g'],
        't': ['r', 'y', 'f', 'g', 'h'],
        'y': ['t', 'u', 'g', 'h', 'j'],
        'u': ['y', 'i', 'h', 'j', 'k'],
        'i': ['u', 'o', 'j', 'k', 'l'],
        'o': ['i', 'p', 'k', 'l'],
        'p': ['o', 'l'],
        'a': ['q', 'w', 's', 'z', 'x'],
        's': ['q', 'w', 'e', 'a', 'd', 'z', 'x', 'c'],
        'd': ['w', 'e', 'r', 's', 'f', 'x', 'c', 'v'],
        'f': ['e', 'r', 't', 'd', 'g', 'c', 'v', 'b'],
        'g': ['r', 't', 'y', 'f', 'h', 'v', 'b', 'n'],
        'h': ['t', 'y', 'u', 'g', 'j', 'b', 'n', 'm'],
        'j': ['y', 'u', 'i', 'h', 'k', 'n', 'm'],
        'k': ['u', 'i', 'o', 'j', 'l', 'm'],
        'l': ['i', 'o', 'p', 'k'],
        'z': ['a', 's', 'x'],
        'x': ['z', 's', 'd', 'c'],
        'c': ['x', 'd', 'f', 'v'],
        'v': ['c', 'f', 'g', 'b'],
        'b': ['v', 'g', 'h', 'n'],
        'n': ['b', 'g', 'h', 'j', 'm'],
        'm': ['n', 'h', 'j', 'k']
    }

class TypoToleranceService:
    def __init__(self, dictionary: Set[str]):
        self.dictionary = dictionary
        self.keyboard = KeyboardLayout()
        self.common_typos = self._load_common_typos()
        
    def correct_query(self, query: str, max_edits: int = 2) -> List[Tuple[str, float]]:
        """
        Correct a query with typo tolerance.
        Returns list of (corrected_query, confidence_score)
        """
        words = query.lower().split()
        corrected_words = []
        
        for word in words:
            if word in self.dictionary:
                corrected_words.append((word, 1.0))
            else:
                corrections = self._suggest_corrections(word, max_edits)
                if corrections:
                    # Take the best correction
                    corrected_words.append(corrections[0])
                else:
                    corrected_words.append((word, 0.0))
        
        # Reconstruct query
        corrected_query = ' '.join([w for w, _ in corrected_words])
        avg_confidence = sum([c for _, c in corrected_words]) / len(corrected_words)
        
        return [(corrected_query, avg_confidence)]
    
    def _suggest_corrections(self, word: str, max_edits: int) -> List[Tuple[str, float]]:
        """Suggest corrections for a misspelled word"""
        candidates = []
        
        # 1. Check edit distance
        for dict_word in self.dictionary:
            distance = lev_distance(word, dict_word)
            if distance <= max_edits:
                confidence = 1.0 / (distance + 1)
                candidates.append((dict_word, confidence))
        
        # 2. Check keyboard adjacency errors
        keyboard_candidates = self._check_keyboard_typos(word)
        candidates.extend(keyboard_candidates)
        
        # 3. Check common typos
        if word in self.common_typos:
            for correct, confidence in self.common_typos[word]:
                candidates.append((correct, confidence))
        
        # Sort by confidence and remove duplicates
        seen = set()
        unique_candidates = []
        for cand, conf in sorted(candidates, key=lambda x: -x[1]):
            if cand not in seen:
                seen.add(cand)
                unique_candidates.append((cand, conf))
        
        return unique_candidates[:5]
    
    def _check_keyboard_typos(self, word: str) -> List[Tuple[str, float]]:
        """Check for typos caused by adjacent keys on keyboard"""
        candidates = []
        
        # Generate possible corrections by replacing each character
        # with adjacent keys on keyboard
        for i in range(len(word)):
            original_char = word[i]
            if original_char in self.keyboard.QWERTY_ADJACENT:
                for adj_char in self.keyboard.QWERTY_ADJACENT[original_char]:
                    # Replace with adjacent character
                    candidate = word[:i] + adj_char + word[i+1:]
                    if candidate in self.dictionary:
                        candidates.append((candidate, 0.8))  # High confidence for keyboard typos
        
        return candidates
    
    def _load_common_typos(self) -> Dict[str, List[Tuple[str, float]]]:
        """Load common typo patterns"""
        # This would be loaded from a database in production
        return {
            'teh': [('the', 0.95)],
            'recieve': [('receive', 0.9)],
            'seperate': [('separate', 0.9)],
            'occured': [('occurred', 0.85)],
            'alot': [('a lot', 0.8)],
        }
    
    def fuzzy_prefix_match(self, prefix: str, dictionary_words: List[str], 
                          max_distance: int = 2) -> List[Tuple[str, int]]:
        """Find words that match a prefix with some fuzziness"""
        matches = []
        
        for word in dictionary_words:
            # Check if word starts with a close match to prefix
            word_prefix = word[:len(prefix)]
            distance = lev_distance(prefix, word_prefix)
            
            if distance <= max_distance:
                matches.append((word, distance))
        
        return sorted(matches, key=lambda x: x[1])