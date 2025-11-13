# nlp_tripagent_frontend

Trip Agent frontend based on Vite + Vue 3 + TypeScript.

## Development

1. Install dependencies:

```bash
npm install
```

2. Start development server:

```bash
npm run dev
```

The backend address is read from the environment variable `VITE_API_BASE_URL`. If not set, it defaults to `http://localhost:8000`.

3. Configure environment variables (optional):

Create `.env.local` file:

```bash
# Backend API address
VITE_API_BASE_URL=http://localhost:8000

# Google Maps API Key (for map visualization)
VITE_GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here

# Whether to use mock data (true/false, default true)
VITE_USE_MOCK_DATA=true
```

**Note**: If Google Maps API Key is not configured, the map functionality will not work. To get API Key:
1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable Maps JavaScript API
3. Create API Key and configure restrictions (recommended to restrict to your domain)

## Directory Structure

```
src/
  main.ts            # Entry point
  App.vue            # Layout and navigation
  router/            # Routing
  stores/            # Pinia stores
  services/          # API clients and business services
  utils/             # Utility functions (includes mock data generator)
  views/             # Itinerary planning / Results display / Map visualization
vite.config.ts       # Vite configuration
```

## Mock Data

This project uses mock data by default (`VITE_USE_MOCK_DATA=true`), allowing you to test functionality without a backend:

- Mock data automatically generates itineraries based on input departure, destination, and number of days
- Supports common city name recognition (e.g., Shanghai, Tokyo, Beijing, etc.)
- Automatically generates map coordinate points and routes
- Includes simulated itinerary arrangements, weather, hotel information, etc.

When the backend is available, set `VITE_USE_MOCK_DATA=false` to switch to the real API.

## Backend API Convention (Example)

- POST `/api/trip/plan` Plan itinerary, body = TripRequest
- GET  `/api/weather?destination=...`
- GET  `/api/scenic-spots?q=...`
- GET  `/api/hotels/recommend?destination=...`

Actual paths can be adjusted in `src/services/tripService.ts`.
