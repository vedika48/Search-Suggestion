from kafka import KafkaConsumer
import json
from datetime import datetime
from typing import Dict
import asyncio
from ..trie import AdvancedTrie
from ..services.personalization_service import PersonalizationService

class SearchEventConsumer:
    def __init__(self, trie: AdvancedTrie, personalization_service: PersonalizationService,
                 bootstrap_servers: str = 'localhost:9092'):
        self.trie = trie
        self.personalization_service = personalization_service
        self.consumer = KafkaConsumer(
            'search-events',
            'click-events',
            bootstrap_servers=bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            auto_offset_reset='latest',
            enable_auto_commit=True,
            group_id='search-suggestion-group'
        )
        
    async def start_consuming(self):
        """Start consuming events from Kafka"""
        for message in self.consumer:
            event = message.value
            
            if message.topic == 'search-events':
                await self._handle_search_event(event)
            elif message.topic == 'click-events':
                await self._handle_click_event(event)
    
    async def _handle_search_event(self, event: Dict):
        """Handle search event"""
        query = event['query']
        user_id = event['user_id']
        timestamp = datetime.fromisoformat(event['timestamp'])
        
        # Update user profile
        await self.personalization_service.update_user_profile(
            user_id, query, event.get('suggestion_clicked')
        )
        
        # Update suggestion frequency if it exists
        suggestion_id = self._find_suggestion_id(query)
        if suggestion_id and suggestion_id in self.trie.suggestions:
            suggestion = self.trie.suggestions[suggestion_id]
            suggestion.frequency += 1
            suggestion.last_updated = timestamp
            
            # Update trending score
            self._update_trending_score(suggestion)
    
    async def _handle_click_event(self, event: Dict):
        """Handle click event"""
        suggestion_id = event['suggestion_id']
        user_id = event['user_id']
        
        if suggestion_id in self.trie.suggestions:
            suggestion = self.trie.suggestions[suggestion_id]
            suggestion.click_count += 1
            
            # Update personalization
            await self.personalization_service.update_user_profile(
                user_id, suggestion.text, suggestion_id
            )
    
    def _update_trending_score(self, suggestion):
        """Update trending score based on recent popularity"""
        # Simplified trending calculation
        # In production, you'd use a more sophisticated algorithm
        # like exponential moving average
        current_time = datetime.now()
        hours_since_update = (current_time - suggestion.last_updated).total_seconds() / 3600
        
        # Decay old score
        suggestion.trending_score *= (0.5 ** (hours_since_update / 24))
        
        # Add new activity
        suggestion.trending_score += 1.0
    
    def _find_suggestion_id(self, query: str) -> str:
        """Find suggestion ID for a query"""
        for sid, suggestion in self.trie.suggestions.items():
            if suggestion.text.lower() == query.lower():
                return sid
        return None