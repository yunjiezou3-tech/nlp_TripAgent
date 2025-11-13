import type { TripRequest, TripResult } from '../stores/trip'

// Mock coordinates for popular cities
const cityCoordinates: Record<string, { lat: number; lng: number }> = {
  'Shanghai': { lat: 31.2304, lng: 121.4737 },
  'Tokyo': { lat: 35.6762, lng: 139.6503 },
  'Beijing': { lat: 39.9042, lng: 116.4074 },
  'Paris': { lat: 48.8566, lng: 2.3522 },
  'New York': { lat: 40.7128, lng: -74.0060 },
  'London': { lat: 51.5074, lng: -0.1278 },
  'Sydney': { lat: -33.8688, lng: 151.2093 },
  'Dubai': { lat: 25.2048, lng: 55.2708 },
  'Singapore': { lat: 1.3521, lng: 103.8198 },
  'Bangkok': { lat: 13.7563, lng: 100.5018 },
  'Hong Kong': { lat: 22.3193, lng: 114.1694 },
  'Seoul': { lat: 37.5665, lng: 126.9780 }
}

// Get city coordinates, return default value if not found
function getCityCoordinates(cityName: string): { lat: number; lng: number } {
  const normalized = cityName.trim()
  for (const [key, coords] of Object.entries(cityCoordinates)) {
    if (normalized.toLowerCase().includes(key.toLowerCase()) || 
        key.toLowerCase().includes(normalized.toLowerCase())) {
      return coords
    }
  }
  // Default return a random coordinate (example: central Asia)
  return { lat: 35.0 + Math.random() * 10, lng: 100.0 + Math.random() * 20 }
}

// Generate mock attraction coordinate points
function generateMapPoints(origin: string, destination: string, days: number): Array<{ lat: number; lng: number; label: string }> {
  const points: Array<{ lat: number; lng: number; label: string }> = []
  
  const originCoords = getCityCoordinates(origin)
  const destCoords = getCityCoordinates(destination)
  
  // Add departure point
  points.push({
    lat: originCoords.lat,
    lng: originCoords.lng,
    label: `Departure: ${origin}`
  })
  
  // Generate intermediate points based on number of days
  for (let i = 1; i <= days; i++) {
    const ratio = i / (days + 1)
    const lat = originCoords.lat + (destCoords.lat - originCoords.lat) * ratio + (Math.random() - 0.5) * 0.5
    const lng = originCoords.lng + (destCoords.lng - originCoords.lng) * ratio + (Math.random() - 0.5) * 0.5
    
    points.push({
      lat,
      lng,
      label: `Day ${i} Attraction`
    })
  }
  
  // Add destination point
  points.push({
    lat: destCoords.lat,
    lng: destCoords.lng,
    label: `Destination: ${destination}`
  })
  
  return points
}

// Generate mock trip data
export function generateMockTripResult(request: TripRequest): TripResult {
  // Regardless of user input, return travel plan from Hong Kong to Seoul
  const origin = 'Hong Kong'
  const destination = 'Seoul'
  const days = 7
  
  const mapPoints = generateMapPoints(origin, destination, days)
  
  // Detailed travel planning data
  const itinerary = {
    title: '7 Days 6 Nights Travel Plan from Hong Kong to Seoul',
    dateRange: 'November 9-15, 2025',
    weather: {
      overview: 'Mid-November Seoul temperature is about 3-15℃, with large temperature differences between day and night. Bring windproof jackets, sweaters, and thermal underwear.',
      dailyForecast: [
        { date: 'Nov 9', condition: 'Cloudy to Sunny', temp: '11-18℃' },
        { date: 'Nov 10', condition: 'Cloudy', temp: '7-13℃' },
        { date: 'Nov 11-12', condition: 'Sunny', temp: '5-14℃' },
        { date: 'Nov 13', condition: 'Sunny', temp: '6-15℃' },
        { date: 'Nov 14-15', condition: 'Cloudy', temp: '5-13℃' }
      ],
      essentials: [
        'T-money transportation card (purchase at airport GS25, includes 4000 KRW card fee)',
        'Power adapter (Korea uses Type C / round two-pin plugs)',
        'Hanbok reservation confirmation (recommend booking 1 month in advance)',
        'N Seoul Tower ticket (optional cable car package)'
      ],
      visa: 'Hong Kong passport visa-free, fill out the Arrival Card and Health Declaration Form upon entry (can fill out K-ETA online in advance)'
    },
    hotels: [
      {
        name: 'Lotte City Hotel Myeongdong',
        location: 'Myeongdong core area, 5 minutes walk to Myeongdong Station, adjacent to Cheonggyecheon Stream and Namsan Tower',
        roomType: 'Standard twin room (about 1200 RMB / night), includes breakfast, some room types overlook Namsan Mountain',
        facilities: 'Gym, rooftop garden, 24-hour front desk (Chinese service available)',
        benefits: 'Book 4 nights or more to enjoy N Seoul Tower ticket + cable car package (about 200 RMB / person discount)'
      },
      {
        name: 'Holiday Inn Express Seoul Hongdae',
        location: 'Direct access to Hongdae Station Exit 5, 3 minutes walk to Hongdae Free Market',
        roomType: 'Superior twin room (about 800 RMB / night), includes breakfast, rooms equipped with air purifiers',
        facilities: '24-hour gym, laundry room, free luggage storage',
        benefits: 'Surrounded by many trendy cafes, nightclubs and fashion boutiques, suitable for young travelers'
      }
    ],
    dailySchedule: [
      {
        day: 1,
        date: 'Nov 9',
        weekday: 'Sunday',
        title: 'Arrive in Seoul → First Experience in Myeongdong',
        morning: [
          'Take Cathay Pacific CX434 from Hong Kong Airport (08:15-12:45), flight time 3.5 hours',
          'Arrive at Incheon Airport, purchase T-money card and recharge 20,000 KRW, take AREX airport express to Seoul Station (about 53 minutes), transfer to subway line 4 to Myeongdong Station (3 stops)'
        ],
        afternoon: [
          'Myeongdong Walking Street: Exit from Myeongdong Station Exit 6, visit Line Friends Store, Olive Young cosmetics store',
          'Lunch recommendation: Wangbijib Korean BBQ (Myeongdong branch)',
          'Namsan Tower: Walk to Namsan Cable Car Station (about 15 minutes), take cable car to the tower (ticket + cable car package about 130 RMB), take photos at the Love Lock Wall, overlook Seoul panorama'
        ],
        evening: [
          'Nanta Show (Myeongdong branch): Book tickets in advance on Hanatour website (about 200 RMB), experience traditional Korean percussion performance',
          'Late night snack: Twosome Place cafe near Myeongdong Station Exit 8, try Korean-style waffles'
        ]
      },
      {
        day: 2,
        date: 'Nov 10',
        weekday: 'Monday',
        title: 'Gyeongbokgung Palace Cultural Day → Bukchon Hanok Village Walk',
        morning: [
          'Gyeongbokgung Palace: Take subway line 3 to Gyeongbokgung Station Exit 5, opens at 9:00 (ticket 3000 KRW), watch the 10:00 Royal Guard Changing Ceremony',
          'National Folk Museum: Free admission, learn about Joseon Dynasty life and culture (adjacent to Gyeongbokgung Palace entrance)'
        ],
        afternoon: [
          'Hanbok experience: Walk to Gookwan Hanbok Photo Studio (Myeongdong branch), choose traditional color hanbok (about 400 RMB / 4 hours, includes hairstyle), take traditional photos at Gyeongbokgung Palace',
          'Bukchon Hanok Village: Walk 15 minutes to Bukchon, explore Gahoe-dong Art Street, recommend visiting the observatory and mural wall from "Bukchon Eight Views"'
        ],
        evening: [
          'Samcheong-dong: Walk to Samcheong-dong Road, dinner try Wangbijib Ginseng Chicken Soup, after dinner browse design brand stores and cultural creative market',
          'Cheonggyecheon Stream night view: Walk 10 minutes from Samcheong-dong to Cheonggyecheon Stream, stroll along the stream to Gwangtong Bridge'
        ]
      },
      {
        day: 3,
        date: 'Nov 11',
        weekday: 'Tuesday',
        title: 'Hongdae Art District → Ewha Womans University',
        morning: [
          'Hongdae Free Market: Open Saturday and Sunday 12:00-18:00, browse handicrafts and independent designer brands (recommend arriving before 11:30)',
          'Hongik University area: Visit Aland, Stylenanda and other trendy stores, lunch recommendation: 8th Floor Burger (Hongdae branch)'
        ],
        afternoon: [
          'Ewha Womans University: Take subway line 2 to Ewha Womans University Station Exit 2, visit Ewha Wall, Sunken Plaza Library, browse Sinchon Women\'s Street',
          'Sinchon food: Try Kyochon Chicken (Sinchon branch) or Kang Ho-dong Baekjeong (Sinchon branch)'
        ],
        evening: [
          'Hongdae nightclubs: Recommend Club Octagon or NB2, experience Korean nightlife (need to carry passport)'
        ]
      },
      {
        day: 4,
        date: 'Nov 12',
        weekday: 'Wednesday',
        title: 'Gangnam Shopping Day → Garosu-gil Road',
        morning: [
          'COEX Aquarium: Take subway line 9 to COEX Station, visit Asia\'s largest aquarium (ticket about 180 RMB), interact with beluga whales',
          'Bongeunsa Temple: Free admission, experience Korean Buddhist culture (10 minutes walk from COEX Mall)'
        ],
        afternoon: [
          'Garosu-gil Road: Take subway line 3 to Sinsa Station Exit 8, visit Gentle Monster flagship store, Aēsop concept store, lunch recommendation: 8th Floor Burger (Gangnam branch)',
          'Garosu-gil cafes: Visit % Arabica or Paul Lafayet, try French desserts'
        ],
        evening: [
          'Dongdaemun Design Plaza (DDP): Visit Zaha Hadid\'s futuristic architecture, visit APM, U:US clothing wholesale markets (open until 5 AM)',
          'Dongdaemun food: Kang Ho-dong Baekjeong (Dongdaemun branch) or Sundae Guk Jjigae (blood sausage stew) near DDP'
        ]
      },
      {
        day: 5,
        date: 'Nov 13',
        weekday: 'Thursday',
        title: 'N Seoul Tower → Gwanghwamun Square',
        morning: [
          'N Seoul Tower (Namsan Seoul Tower): Take subway line 3 to Dongguk University Station Exit 1, walk 30 minutes or take cable car to the top, take panoramic photos of Seoul from N Seoul Tower observatory',
          'Itaewon: Take subway line 6 to Itaewon Station Exit 1, visit trendy stores, try authentic Indian curry'
        ],
        afternoon: [
          'Gwanghwamun Square: Visit King Sejong Statue, Admiral Yi Sun-sin Statue, watch the 14:00 Gwanghwamun Gate Guard Changing Ceremony',
          'National Museum of Korea: Free admission (reservation required), learn about Korean historical artifacts (10 minutes walk to Gwanghwamun Station)'
        ],
        evening: [
          'Jongno-gu food: Try Tosokchon Ginseng Chicken Soup (Jongno branch) or Myeongdong Wangbijib Korean BBQ (Jongno branch)'
        ]
      },
      {
        day: 6,
        date: 'Nov 14',
        weekday: 'Friday',
        title: 'Mural Village Walk → Dragon Hill Spa',
        morning: [
          'Ihwa Mural Village: Take subway line 4 to Hyehwa Station Exit 2, follow signs and walk 30 minutes to mural village, visit "Castle in the Sky" stairs and carp flags',
          'Naksan Park: Walk 15 minutes from mural village to Naksan Park, overlook Seoul panorama'
        ],
        afternoon: [
          'Dragon Hill Spa: Take subway line 1 to Yongsan Station, experience Korean sauna (ticket about 100 RMB, includes towel and sauna clothes)',
          'After sauna activities: Enjoy sweet rice drink, boiled eggs in the rest area, or experience body scrub service (additional fee required)'
        ],
        evening: [
          'Yongsan Electronics Market: Buy Korean cosmetics, small appliances, recommend OLIVE YOUNG and GS Mart',
          'Dinner: Wangbijib Korean BBQ (Yongsan branch) or Yukgaejang (spicy beef soup) near Yongsan Station'
        ]
      },
      {
        day: 7,
        date: 'Nov 15',
        weekday: 'Saturday',
        title: 'Return Day → Duty-free Shopping',
        morning: [
          'Lotte Duty Free Myeongdong: Opens at 9:30, get coupons with passport and flight information, buy Korean skincare products (like Sulwhasoo, Whoo) and health products',
          'Myeongdong food: Lunch recommendation Sundae Guk Jjigae (blood sausage stew) or Ramen Factory'
        ],
        afternoon: [
          'Take airport express AREX to Incheon Airport (about 53 minutes), arrive 3 hours in advance for tax refund (tax refund counter near Gate 28)',
          'Restock at Incheon Airport duty-free shops (recommend Shilla Duty Free, some items cheaper than downtown)'
        ],
        evening: [
          'Take Cathay Pacific CX418 (18:35-22:05) back to Hong Kong, end of trip'
        ]
      }
    ],
    transportation: {
      subway: 'Seoul subway has extensive coverage, fare starts from 1250 KRW, 10% discount with T-money card. Recommend downloading "Naver Map" or "Subway Korea" APP for route planning.',
      airport: [
        'Incheon Airport to Myeongdong: Take AREX airport express to Seoul Station (47 minutes), transfer to subway line 4 to Myeongdong Station (3 stops), total cost about 8000 KRW.',
        'Incheon Airport to Hongdae: Take AREX airport express to Hongik University Station (52 minutes), direct access to Exit 5, total cost about 9000 KRW.'
      ],
      taxi: 'Base fare 3800 KRW (within 2 km), 20% surcharge during late night (22:00-04:00). Recommend using Kakao T taxi APP (supports Chinese).'
    },
    foodMap: {
      koreanBbq: 'Wangbijib Korean BBQ (Myeongdong branch), Kang Ho-dong Baekjeong (Hongdae branch)',
      koreanSetMeal: 'Tosokchon Ginseng Chicken Soup (Jongno branch), Wangbijib Ginseng Chicken Soup (Samcheong-dong branch)',
      streetFood: 'Myeongdong spicy rice cakes, Hongdae potato hot dogs, Gwangjang Market mung bean pancakes',
      dessert: 'Baskin Robbins banana milk ice cream, Hongdae Twosome Place waffles'
    },
    notes: {
      taxRefund: 'Tax refund available for purchases over 30,000 KRW, keep tax refund forms and receipts, get customs stamp at airport then process at tax refund machine or counter (cash refund requires queuing).',
      hanbokExperience: 'Recommend Gookwan, Hanbok Rental (Myeongdong branch), need advance reservation, choose lightweight styles for easy walking.',
      safety: 'Seoul has good public security, but pay attention to belongings, avoid showing valuables in crowded places.',
      communication: 'Purchase EGG mobile WiFi at airport convenience store (about 50 RMB / day), or activate Hong Kong mobile roaming (recommend purchasing CMLink Korea short-term package).'
    },
    budget: {
      airfare: 'Round trip about 2500 RMB (Cathay Pacific morning flight)',
      hotel: '6 nights about 6000 RMB (4 nights Myeongdong + 2 nights Hongdae)',
      food: 'About 3000 RMB (daily average 400-500 RMB)',
      tickets: 'About 1000 RMB (includes N Seoul Tower, Nanta Show, hanbok experience)',
      transportation: 'About 1000 RMB (includes airport express, subway, taxi)',
      total: 'About 13500 RMB (per person)'
    }
  }
  
  return {
    itinerary,
    mapPoints,
    raw: {
      request: { origin, destination, days },
      generatedAt: new Date().toISOString()
    }
  }
}

