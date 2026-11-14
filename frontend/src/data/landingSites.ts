// Successful NASA Mars landings, shown in the "Whole Mars" view.
//
// Coordinates: planetocentric latitude, east-positive longitude in −180…180° (the app's one
// convention, see src/mars.ts), rounded from published landing-site positions. They are
// approximate (±~0.1°): good for a global overview, not for navigation. Curiosity uses the
// same Bradbury Landing position as the rest of the app (app/science.py).

export interface LandingSite {
  id: string
  mission: string
  vehicle: string
  year: number
  lat: number
  lon: number
  place: string
  note: string
}

export const LANDING_SITES: LandingSite[] = [
  {
    id: 'curiosity', mission: 'Curiosity (Mars Science Laboratory)', vehicle: 'Rover', year: 2012,
    lat: -4.5895, lon: 137.4417, place: 'Bradbury Landing, Gale Crater',
    note: 'Our study area. Still driving up Aeolis Mons (Mount Sharp).',
  },
  {
    id: 'perseverance', mission: 'Perseverance (Mars 2020)', vehicle: 'Rover + Ingenuity helicopter', year: 2021,
    lat: 18.4447, lon: 77.4508, place: 'Octavia E. Butler Landing, Jezero Crater',
    note: 'Ancient river delta; collecting samples for return to Earth.',
  },
  {
    id: 'viking1', mission: 'Viking 1', vehicle: 'Lander', year: 1976,
    lat: 22.27, lon: -47.95, place: 'Chryse Planitia',
    note: 'First successful US landing on Mars.',
  },
  {
    id: 'viking2', mission: 'Viking 2', vehicle: 'Lander', year: 1976,
    lat: 47.64, lon: 134.29, place: 'Utopia Planitia',
    note: 'Photographed seasonal frost at the landing site.',
  },
  {
    id: 'pathfinder', mission: 'Mars Pathfinder', vehicle: 'Lander + Sojourner rover', year: 1997,
    lat: 19.13, lon: -33.22, place: 'Ares Vallis',
    note: 'First rover on Mars (Sojourner).',
  },
  {
    id: 'spirit', mission: 'Spirit (MER-A)', vehicle: 'Rover', year: 2004,
    lat: -14.5684, lon: 175.4726, place: 'Gusev Crater',
    note: 'Found silica-rich deposits near Home Plate.',
  },
  {
    id: 'opportunity', mission: 'Opportunity (MER-B)', vehicle: 'Rover', year: 2004,
    lat: -1.9462, lon: -5.5266, place: 'Meridiani Planum (Eagle crater)',
    note: 'Drove over 45 km in 14 years; found hematite "blueberries".',
  },
  {
    id: 'phoenix', mission: 'Phoenix', vehicle: 'Lander', year: 2008,
    lat: 68.22, lon: -125.70, place: 'Vastitas Borealis',
    note: 'Touched and confirmed water ice just below the surface.',
  },
]
