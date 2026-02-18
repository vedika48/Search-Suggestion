from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from datetime import datetime
import uuid
import redis.asyncio as redis
from ..trie import AdvancedTrie
from ..services.personalization_service import PersonalizationService
from ..services.typo_tolerance import TypoToleranceService
from ..kafka.producer import SearchEventProducer
from ..models.models import Suggestion, UserProfile

app = FastAPI(title="Real-Time Search Suggestion API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
trie = AdvancedTrie()
personalization_service = PersonalizationService(redis_client)
typo_service = TypoToleranceService(set())  # Would load dictionary
kafka_producer = SearchEventProducer()

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    # Load dictionary for typo tolerance
    dictionary = await load_dictionary()
    typo_service.dictionary = dictionary
    
    # Load suggestions into Trie
    suggestions = await load_suggestions()
    for suggestion in suggestions:
        trie.insert(suggestion)

@app.get("/suggest")
async def get_suggestions(
    request: Request,
    q: str = Query(..., min_length=1, max_length=100),
    user_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
    category: Optional[str] = Query(None)
):
    """Get search suggestions"""
    
    # Get or create session
    if not session_id:
        session_id = str(uuid.uuid4())
    
    if user_id:
        session = await personalization_service.create_session(user_id, session_id)
        user_profile = await personalization_service.get_user_profile(user_id)
    else:
        session = None
        user_profile = None
    
    # Build context
    context = {
        'time_of_day': datetime.now().hour,
        'category': category
    }
    if lat and lon:
        context['location'] = {'lat': lat, 'lon': lon}
    
    # Check for typos
    if typo_service.dictionary:
        corrections = typo_service.correct_query(q)
        if corrections and corrections[0][1] < 0.9:  # Low confidence in original
            # Use corrected query
            corrected_q, confidence = corrections[0]
            if confidence > 0.6:
                # Store original for UI
                context['original_query'] = q
                q = corrected_q
    
    # Get suggestions from Trie
    suggestions = trie.get_suggestions_with_score(
        q, user_profile, session, context
    )
    
    # Apply personalization
    if user_profile and session:
        suggestions = personalization_service.get_personalized_ranking(
            suggestions, user_profile, session
        )
    
    # Send search event to Kafka
    kafka_producer.send_search_event(user_id or 'guest', q)
    
    # Format response
    response = {
        'query': q,
        'session_id': session_id,
        'suggestions': [
            {
                'id': s.id,
                'text': s.text,
                'category': s.category,
                'score': s.score
            }
            for s in suggestions
        ]
    }
    
    if 'original_query' in context:
        response['original_query'] = context['original_query']
        response['did_you_mean'] = q
    
    return response

@app.post("/click")
async def record_click(
    suggestion_id: str,
    query: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    position: int = 0
):
    """Record a click on a suggestion"""
    
    # Send click event to Kafka
    kafka_producer.send_click_event(
        user_id or 'guest',
        query,
        suggestion_id,
        position
    )
    
    # Update session if exists
    if session_id:
        await personalization_service.update_session(
            session_id, query, suggestion_id
        )
    
    return {"status": "success"}

@app.post("/suggestions")
async def add_suggestion(suggestion: Suggestion):
    """Add a new suggestion to the system"""
    trie.insert(suggestion)
    return {"status": "success", "id": suggestion.id}

@app.get("/trending")
async def get_trending_suggestions(
    limit: int = Query(10, ge=1, le=100),
    category: Optional[str] = None
):
    """Get trending suggestions"""
    suggestions = list(trie.suggestions.values())
    
    # Filter by category if specified
    if category:
        suggestions = [s for s in suggestions if s.category == category]
    
    # Sort by trending score
    suggestions.sort(key=lambda x: x.trending_score, reverse=True)
    
    return {
        'trending': [
            {
                'text': s.text,
                'trending_score': s.trending_score,
                'category': s.category
            }
            for s in suggestions[:limit]
        ]
    }

async def load_dictionary() -> set:
    """Load dictionary words for typo tolerance"""
    # In production, load from database or file
    return {
        'python', 'java', 'javascript', 'spring', 'django',
        'restaurant', 'pizza', 'movie', 'netflix', 'amazon'
    }

async def load_suggestions() -> List[Suggestion]:
    """Load initial suggestions"""
    # In production, load from database
    return [
        Suggestion(
            id='1',
            text='python programming',
            category='technology',
            frequency=1000,
            click_count=800
        ),
        Suggestion(
            id='2',
            text='java spring boot',
            category='technology',
            frequency=800,
            click_count=600
        ),
        Suggestion(
            id='3',
            text='pizza near me',
            category='food',
            frequency=500,
            click_count=400
        ),
        # Add more suggestions...
    ]

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    kafka_producer.close()
    await redis_client.close()