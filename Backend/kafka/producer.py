from kafka import KafkaProducer
import json
from datetime import datetime
from typing import Dict, Any

class SearchEventProducer:
    def __init__(self, bootstrap_servers: str = 'localhost:9092'):
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all',
            retries=3
        )
        
    def send_search_event(self, user_id: str, query: str, 
                          suggestion_clicked: str = None):
        """Send search event to Kafka"""
        event = {
            'event_type': 'search',
            'user_id': user_id,
            'query': query,
            'suggestion_clicked': suggestion_clicked,
            'timestamp': datetime.now().isoformat()
        }
        
        future = self.producer.send('search-events', event)
        future.add_callback(self._on_send_success)
        future.add_errback(self._on_send_error)
        
    def send_click_event(self, user_id: str, query: str, 
                         suggestion_id: str, position: int):
        """Send click event to Kafka"""
        event = {
            'event_type': 'click',
            'user_id': user_id,
            'query': query,
            'suggestion_id': suggestion_id,
            'position': position,
            'timestamp': datetime.now().isoformat()
        }
        
        self.producer.send('click-events', event)
    
    def _on_send_success(self, record_metadata):
        print(f"Message sent to {record_metadata.topic}")
        
    def _on_send_error(self, exc):
        print(f"Error sending message: {exc}")
        
    def close(self):
        self.producer.close()