import React, { useState, useEffect, useCallback, useRef } from 'react';
import debounce from 'lodash/debounce';
import './SearchSuggestions.css';

const SearchSuggestions = ({ 
  userId, 
  onSearch,
  placeholder = "Search...",
  maxSuggestions = 10
}) => {
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [showDidYouMean, setShowDidYouMean] = useState(false);
  const [originalQuery, setOriginalQuery] = useState('');
  
  const inputRef = useRef(null);
  const abortControllerRef = useRef(null);

  // Initialize session
  useEffect(() => {
    setSessionId(localStorage.getItem('searchSessionId') || 
                 `session_${Date.now()}_${Math.random().toString(36)}`);
  }, []);

  // Get user location
  const [location, setLocation] = useState(null);
  useEffect(() => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setLocation({
            lat: pos.coords.latitude,
            lon: pos.coords.longitude
          });
        },
        (err) => console.log('Location permission denied')
      );
    }
  }, []);

  // Debounced search function
  const fetchSuggestions = useCallback(
    debounce(async (searchQuery) => {
      if (!searchQuery || searchQuery.length < 2) {
        setSuggestions([]);
        return;
      }

      // Cancel previous request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      abortControllerRef.current = new AbortController();

      try {
        setLoading(true);
        
        // Build query params
        const params = new URLSearchParams({
          q: searchQuery,
          ...(userId && { user_id: userId }),
          ...(sessionId && { session_id: sessionId }),
          ...(location && { lat: location.lat, lon: location.lon })
        });

        const response = await fetch(
          `http://localhost:8000/suggest?${params}`,
          { signal: abortControllerRef.current.signal }
        );

        if (!response.ok) throw new Error('Network response was not ok');

        const data = await response.json();
        
        setSuggestions(data.suggestions || []);
        setSessionId(data.session_id);
        localStorage.setItem('searchSessionId', data.session_id);
        
        // Handle "did you mean" suggestions
        if (data.did_you_mean && data.original_query) {
          setShowDidYouMean(true);
          setOriginalQuery(data.original_query);
        }
        
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.error('Error fetching suggestions:', error);
        }
      } finally {
        setLoading(false);
      }
    }, 300),
    [userId, sessionId, location]
  );

  // Handle input change
  const handleInputChange = (e) => {
    const value = e.target.value;
    setQuery(value);
    setSelectedIndex(-1);
    setShowDidYouMean(false);
    fetchSuggestions(value);
  };

  // Handle key navigation
  const handleKeyDown = (e) => {
    if (suggestions.length === 0) return;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev => 
          prev < suggestions.length - 1 ? prev + 1 : prev
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => prev > -1 ? prev - 1 : -1);
        break;
      case 'Enter':
        e.preventDefault();
        if (selectedIndex >= 0) {
          handleSuggestionClick(suggestions[selectedIndex]);
        } else {
          handleSearch(query);
        }
        break;
      case 'Escape':
        setSuggestions([]);
        setSelectedIndex(-1);
        break;
    }
  };

  // Handle suggestion click
  const handleSuggestionClick = async (suggestion) => {
    setQuery(suggestion.text);
    setSuggestions([]);
    
    // Record click event
    try {
      await fetch('http://localhost:8000/click', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          suggestion_id: suggestion.id,
          query: suggestion.text,
          user_id: userId,
          session_id: sessionId,
          position: suggestions.indexOf(suggestion)
        })
      });
    } catch (error) {
      console.error('Error recording click:', error);
    }
    
    // Trigger search
    if (onSearch) {
      onSearch(suggestion.text);
    }
  };

  // Handle search
  const handleSearch = (searchQuery) => {
    setSuggestions([]);
    if (onSearch) {
      onSearch(searchQuery);
    }
  };

  // Handle "did you mean" click
  const handleDidYouMeanClick = () => {
    setQuery(originalQuery);
    fetchSuggestions(originalQuery);
  };

  return (
    <div className="search-container">
      <div className="search-input-wrapper">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="search-input"
          autoComplete="off"
        />
        {loading && <div className="loading-spinner" />}
      </div>

      {showDidYouMean && (
        <div className="did-you-mean">
          Did you mean:{' '}
          <button onClick={handleDidYouMeanClick} className="did-you-mean-link">
            {originalQuery}
          </button>
        </div>
      )}

      {suggestions.length > 0 && (
        <ul className="suggestions-list">
          {suggestions.map((suggestion, index) => (
            <li
              key={suggestion.id}
              className={`suggestion-item ${index === selectedIndex ? 'selected' : ''}`}
              onClick={() => handleSuggestionClick(suggestion)}
              onMouseEnter={() => setSelectedIndex(index)}
            >
              <div className="suggestion-content">
                <span className="suggestion-text">{suggestion.text}</span>
                <span className="suggestion-category">{suggestion.category}</span>
              </div>
              <div className="suggestion-score">
                {Math.round(suggestion.score * 100)}% match
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default SearchSuggestions;