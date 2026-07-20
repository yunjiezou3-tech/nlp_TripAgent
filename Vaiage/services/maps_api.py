import os
from urllib.parse import quote

import googlemaps
import requests


class POIApi:
    def __init__(self, api_key=None, gmaps_client=None, http_get=None):
        """Initialize Points of Interest API with Google Maps client"""
        self.api_key = api_key or os.environ.get("MAPS_API_KEY")
        if gmaps_client is not None:
            self.gmaps = gmaps_client
        elif self.api_key:
            self.gmaps = googlemaps.Client(key=self.api_key)
        else:
            self.gmaps = None
        self._http_get = http_get if http_get is not None else requests.get
    
    def get_poi(self, location, radius=1000, keyword=None, type=None, language="en", min_price=None, max_price=None):
        """
        Search for points of interest near a location
        
        Args:
            location: The latitude/longitude or address to search around
            radius: Distance in meters within which to search
            keyword: Term to search for (e.g. "museum", "restaurant")
            type: Restricts results to places matching the specified type (e.g. "tourist_attraction")
            language: The language in which to return results
            min_price: Minimum price level (0-4)
            max_price: Maximum price level (0-4)
            
        Returns:
            Dictionary containing search results
        """
        params = {
            'location': location,
            'radius': radius,
            'language': language
        }
        
        if keyword:
            params['query'] = keyword  # Changed from 'keyword' to 'query'
        if type:
            params['type'] = type
        if min_price is not None:
            params['min_price'] = min_price
        if max_price is not None:
            params['max_price'] = max_price
            
        return self.gmaps.places(**params)
    
    def get_poi_details(self, place_id, language="en", fields=None):
        """
        Get detailed information about a specific place
        
        Args:
            place_id: The Google Place ID
            language: The language in which to return results
            fields: List of fields to include in the response
            
        Returns:
            Dictionary containing place details
        """
        params = {
            'place_id': place_id,
            'language': language
        }
        
        if fields:
            params['fields'] = fields
            
        return self.gmaps.place(**params)
    
    def get_poi_reviews(self, place_id, language="en", max_reviews=5):
        """
        Get reviews for a specific place
        
        Args:
            place_id: The Google Place ID
            language: The language in which to return results
            max_reviews: Maximum number of reviews to return
            
        Returns:
            Dictionary containing place reviews
        """
        result = self.gmaps.place(
            place_id=place_id,
            language=language,
            fields=['review'],
            reviews_sort="newest"
        )
        
        # Limit the number of reviews returned
        if 'result' in result and 'reviews' in result['result']:
            result['result']['reviews'] = result['result']['reviews'][:max_reviews]
            
        return result
    
    def get_nearby_places(
        self,
        location=None,
        type=None,
        radius=1000,
        language="en",
        page_token=None,
        keyword=None,
    ):
        """
        Find places of a specific type near a location
        
        Args:
            location: The latitude/longitude or address to search around
            type: Type of place to search for (e.g. "restaurant", "museum")
            radius: Distance in meters within which to search
            language: The language in which to return results
            
        Returns:
            List of nearby places
        """
        if page_token:
            return self.gmaps.places_nearby(page_token=page_token)

        params = {
            "location": location,
            "radius": radius,
            "type": type,
            "language": language,
        }
        if keyword:
            params["keyword"] = keyword
        return self.gmaps.places_nearby(**params)

    def get_place_price_range(self, place_id, language="zh-CN"):
        """Return Places API New priceRange metadata when it is available."""
        if not self.api_key or not place_id:
            return None

        encoded_place_id = quote(str(place_id), safe="")
        url = f"https://places.googleapis.com/v1/places/{encoded_place_id}"
        try:
            response = self._http_get(
                url,
                headers={
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": "priceRange",
                },
                params={"languageCode": language},
                timeout=5,
            )
            if getattr(response, "status_code", None) != 200:
                return None
            payload = response.json()
        except Exception:
            return None

        if not isinstance(payload, dict):
            return None
        price_range = payload.get("priceRange")
        return price_range if isinstance(price_range, dict) else None
    
    def get_distance_matrix(self, origins, destinations, mode="driving", language="en", units="metric"):
        """
        Calculate distance and duration between multiple origins and destinations
        
        Args:
            origins: List of addresses or lat/lng values
            destinations: List of addresses or lat/lng values
            mode: Travel mode (driving, walking, bicycling, transit)
            language: The language in which to return results
            units: Unit system for distances (metric, imperial)
            
        Returns:
            Distance matrix results
        """
        return self.gmaps.distance_matrix(
            origins=origins,
            destinations=destinations,
            mode=mode,
            language=language,
            units=units
        )
    
    def get_place_photos(self, photo_reference, max_width=400, max_height=400):
        """
        Get photos for a place
        
        Args:
            photo_reference: Photo reference from a Place Search or Details response
            max_width: Maximum width of the image
            max_height: Maximum height of the image
            
        Returns:
            URL to the photo
        """
        return self.gmaps.places_photo(
            photo_reference=photo_reference,
            max_width=max_width,
            max_height=max_height
        )
