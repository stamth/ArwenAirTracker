# -*- coding: utf-8 -*-

# Diccionario con información de aeropuertos
AEROPUERTOS = {
    "SAEZ": {"nombre": "Ezeiza", "ciudad": "Buenos Aires", "pais": "Argentina", "provincia": "Buenos Aires", "lat": -34.8222, "lon": -58.5358},
    "SABE": {"nombre": "Aeroparque", "ciudad": "Buenos Aires", "pais": "Argentina", "provincia": "CABA", "lat": -34.5592, "lon": -58.4156},
    "SACO": {"nombre": "Córdoba", "ciudad": "Córdoba", "pais": "Argentina", "provincia": "Córdoba", "lat": -31.3236, "lon": -64.2083},
    "SAME": {"nombre": "Mendoza", "ciudad": "Mendoza", "pais": "Argentina", "provincia": "Mendoza", "lat": -32.8317, "lon": -68.7928},
    "SASA": {"nombre": "Salta", "ciudad": "Salta", "pais": "Argentina", "provincia": "Salta", "lat": -24.8560, "lon": -65.4861},
    "SANT": {"nombre": "Tucumán", "ciudad": "San Miguel de Tucumán", "pais": "Argentina", "provincia": "Tucumán", "lat": -26.8409, "lon": -65.1048},
    "SAWH": {"nombre": "Ushuaia", "ciudad": "Ushuaia", "pais": "Argentina", "provincia": "Tierra del Fuego", "lat": -54.8433, "lon": -68.2958},
    "SAVB": {"nombre": "El Calafate", "ciudad": "El Calafate", "pais": "Argentina", "provincia": "Santa Cruz", "lat": -50.2803, "lon": -72.0531},
    "SAZS": {"nombre": "Bariloche", "ciudad": "San Carlos de Bariloche", "pais": "Argentina", "provincia": "Río Negro", "lat": -41.1511, "lon": -71.1578},
    "SAVC": {"nombre": "Comodoro Rivadavia", "ciudad": "Comodoro Rivadavia", "pais": "Argentina", "provincia": "Chubut", "lat": -45.7853, "lon": -67.4656},
    "SARP": {"nombre": "Posadas", "ciudad": "Posadas", "pais": "Argentina", "provincia": "Misiones", "lat": -27.3858, "lon": -55.9708},
    "SARC": {"nombre": "Resistencia", "ciudad": "Resistencia", "pais": "Argentina", "provincia": "Chaco", "lat": -27.4500, "lon": -59.0561},
    "SARF": {"nombre": "Formosa", "ciudad": "Formosa", "pais": "Argentina", "provincia": "Formosa", "lat": -26.2125, "lon": -58.2277},
    "SAWG": {"nombre": "Río Gallegos", "ciudad": "Río Gallegos", "pais": "Argentina", "provincia": "Santa Cruz", "lat": -51.6088, "lon": -69.3125},
    "SAZR": {"nombre": "Santa Rosa", "ciudad": "Santa Rosa", "pais": "Argentina", "provincia": "La Pampa", "lat": -36.5916, "lon": -64.2763},
    "SAVV": {"nombre": "Viedma", "ciudad": "Viedma", "pais": "Argentina", "provincia": "Río Negro", "lat": -40.8694, "lon": -63.0000},
    "SAZN": {"nombre": "Neuquén", "ciudad": "Neuquén", "pais": "Argentina", "provincia": "Neuquén", "lat": -38.9488, "lon": -68.1555},
    "SASJ": {"nombre": "Jujuy", "ciudad": "San Salvador de Jujuy", "pais": "Argentina", "provincia": "Jujuy", "lat": -24.3922, "lon": -65.1000},
    "SAAR": {"nombre": "Rosario", "ciudad": "Rosario", "pais": "Argentina", "provincia": "Santa Fe", "lat": -32.9036, "lon": -60.7844},
    "SAAP": {"nombre": "Paraná", "ciudad": "Paraná", "pais": "Argentina", "provincia": "Entre Ríos", "lat": -31.7847, "lon": -60.4803},
    "SAOC": {"nombre": "Río Cuarto", "ciudad": "Río Cuarto", "pais": "Argentina", "provincia": "Córdoba", "lat": -33.0853, "lon": -64.3439},
    "SAVT": {"nombre": "Puerto Madryn", "ciudad": "Puerto Madryn", "pais": "Argentina", "provincia": "Chubut", "lat": -42.7592, "lon": -65.0500},
    "SAZM": {"nombre": "Mar del Plata", "ciudad": "Mar del Plata", "pais": "Argentina", "provincia": "Buenos Aires", "lat": -37.9343, "lon": -57.5738},
    "SAOU": {"nombre": "San Luis", "ciudad": "San Luis", "pais": "Argentina", "provincia": "San Luis", "lat": -33.2825, "lon": -66.3875},
    "SANL": {"nombre": "La Rioja", "ciudad": "La Rioja", "pais": "Argentina", "provincia": "La Rioja", "lat": -29.4140, "lon": -66.7835},
    "SADF": {"nombre": "San Fernando", "ciudad": "San Fernando", "pais": "Argentina", "provincia": "Buenos Aires", "lat": -34.4447, "lon": -58.5343},
    "SADP": {"nombre": "Base Aérea El Palomar", "ciudad": "El Palomar", "pais": "Argentina", "provincia": "Buenos Aires", "lat": -34.6783, "lon": -58.5738},
    "SADM": {"nombre": "Base Aérea Morón", "ciudad": "Morón", "pais": "Argentina", "provincia": "Buenos Aires", "lat": -34.6567, "lon": -58.6197},
    "SCEL": {"nombre": "Santiago Chile", "ciudad": "Santiago", "pais": "Chile", "lat": -33.3930, "lon": -70.7858},
    "SBGR": {"nombre": "São Paulo Brasil", "ciudad": "São Paulo", "pais": "Brasil", "lat": -23.4356, "lon": -46.4731},
    "KMIA": {"nombre": "Miami EE.UU.", "ciudad": "Miami", "pais": "Estados Unidos", "lat": 25.7959, "lon": -80.2870},
    "KJFK": {"nombre": "Nueva York EE.UU.", "ciudad": "Nueva York", "pais": "Estados Unidos", "lat": 40.6413, "lon": -73.7781},
    "LEMD": {"nombre": "Madrid España", "ciudad": "Madrid", "pais": "España", "lat": 40.4936, "lon": -3.5668},
    "SUAA": {"nombre": "Montevideo Uruguay", "ciudad": "Montevideo", "pais": "Uruguay", "lat": -34.8384, "lon": -56.0308},
    "SPIM": {"nombre": "Lima Perú", "ciudad": "Lima", "pais": "Perú", "lat": -12.0219, "lon": -77.1143},
}

# Mantener AEROPUERTOS_COORDS por compatibilidad si es necesario, pero ahora AEROPUERTOS tiene las keys lat/lon
AEROPUERTOS_COORDS = {k: (v['lat'], v['lon']) for k, v in AEROPUERTOS.items()}
