# -*- coding: utf-8 -*-

# Base de datos de aeronaves oficiales y gubernamentales de Argentina
AERONAVES_DATA = [
    # PRESIDENCIALES
    ("ARG-01", "ARG-01 (Ex T-01)", "Presidencia de la Nacion", "Nacional", "Boeing", "737-800 BBJ", 50000000, 15000, 3200, 8000),
    ("ARG-02", "ARG-02 (Ex T-02)", "Presidencia de la Nacion", "Nacional", "Boeing", "737-500", 15000000, 12000, 2800, 7100),
    ("ARG-03", "ARG-03 (Ex T-03)", "Presidencia de la Nacion", "Nacional", "Bombardier", "Learjet 60", 3500000, 5200, 800, 2000),
    ("ARG-10", "ARG-10 (Helicoptero)", "Presidencia de la Nacion", "Nacional", "Sikorsky", "S-70 Black Hawk", 12000000, 4500, 600, 1500),
    ("ARG-11", "ARG-11 (Helicoptero)", "Presidencia de la Nacion", "Nacional", "Sikorsky", "S-76", 8000000, 3800, 500, 1250),
    ("ARG-12", "ARG-12 (Helicoptero)", "Presidencia de la Nacion", "Nacional", "Sikorsky", "S-76", 8000000, 3800, 500, 1250),
    
    # PROVINCIALES
    ("LQ-BFS", "LQ-BFS (Tucuman)", "Gobierno de Tucuman", "Tucuman", "Bombardier", "Learjet 60", 3500000, 5200, 800, 2000),
    ("LQ-BFU", "LQ-BFU (Buenos Aires)", "Gobierno de Buenos Aires", "Buenos Aires", "Eurocopter", "EC-145", 6000000, 2800, 350, 880),
    ("LQ-BIF", "LQ-BIF (San Juan)", "Gobierno de San Juan", "San Juan", "Cessna", "Citation V", 2500000, 4800, 750, 1880),
    ("LQ-BIN", "LQ-BIN (Santa Fe)", "Gobierno de Santa Fe", "Santa Fe", "Eurocopter", "AS-350", 2500000, 1800, 220, 550),
    ("LQ-CFI", "LQ-CFI (Chaco)", "Gobierno de Chaco", "Chaco", "Learjet", "60 XR", 4500000, 5200, 800, 2000),
    ("LQ-CHQ", "LQ-CHQ (Formosa)", "Gobierno de Formosa", "Formosa", "Learjet", "60", 3500000, 5200, 800, 2000),
    ("LQ-CJS", "LQ-CJS (Salta)", "Gobierno de Salta", "Salta", "Bombardier", "Learjet 45 XR", 4200000, 4500, 700, 1750),
    ("LQ-COW", "LQ-COW (Chubut)", "Gobierno de Chubut", "Chubut", "Learjet", "45", 3800000, 4500, 700, 1750),
    ("LQ-COZ", "LQ-COZ (Santiago)", "Gobierno de Santiago del Estero", "Santiago del Estero", "Eurocopter", "AS-350", 2500000, 1800, 220, 550),
    ("LQ-CPL", "LQ-CPL (La Rioja)", "Gobierno de La Rioja", "La Rioja", "Learjet", "60", 3500000, 5200, 800, 2000),
    ("LQ-CPS", "LQ-CPS (Cordoba)", "Gobierno de Cordoba", "Cordoba", "Bombardier", "Learjet 60 XR", 4800000, 5200, 800, 2000),
    ("LQ-CZX", "LQ-CZX (Mendoza)", "Gobierno de Mendoza", "Mendoza", "Learjet", "31A", 1200000, 3500, 600, 1500),
    ("LQ-FDP", "LQ-FDP (Entre Rios)", "Gobierno de Entre Rios", "Entre Rios", "Learjet", "60", 3500000, 5200, 800, 2000),
    ("LQ-FJV", "LQ-FJV (Buenos Aires)", "Gobierno de Buenos Aires", "Buenos Aires", "Eurocopter", "AS-365 Dauphin", 4500000, 2500, 320, 800),
    ("LQ-JVJ", "LQ-JVJ (Buenos Aires)", "Gobierno de Buenos Aires", "Buenos Aires", "Airbus", "H145E", 8000000, 2000, 350, 880),
    ("LQ-FOH", "LQ-FOH (Neuquen)", "Gobierno de Neuquen", "Neuquen", "Learjet", "45", 3800000, 4500, 700, 1750),
    ("LQ-FVO", "LQ-FVO (Cordoba)", "Gobierno de Cordoba", "Cordoba", "Eurocopter", "AS-350", 2500000, 1800, 220, 550),
    ("LQ-GDR", "LQ-GDR (San Luis)", "Gobierno de San Luis", "San Luis", "Learjet", "60", 3500000, 5200, 800, 2000),
    ("LQ-GHL", "LQ-GHL (Jujuy)", "Gobierno de Jujuy", "Jujuy", "Learjet", "31A", 1200000, 3500, 600, 1500),
    ("LQ-GZJ", "LQ-GZJ (Santa Cruz)", "Gobierno de Santa Cruz", "Santa Cruz", "Beechcraft", "B-350 King Air", 4200000, 2200, 350, 880),
    ("LQ-GZP", "LQ-GZP (Misiones)", "Gobierno de Misiones", "Misiones", "Learjet", "45", 3800000, 4500, 700, 1750),
    ("LQ-GZZ", "LQ-GZZ (Rio Negro)", "Gobierno de Rio Negro", "Rio Negro", "Cessna", "Citation V", 2500000, 4800, 750, 1880),
    ("LQ-HRO", "LQ-HRO (Cordoba)", "Gobierno de Cordoba", "Cordoba", "Eurocopter", "AS-350", 2500000, 1800, 220, 550),
    ("LQ-IFA", "LQ-IFA (Catamarca)", "Gobierno de Catamarca", "Catamarca", "Learjet", "75", 9500000, 4800, 750, 1880),
    ("LQ-KID", "LQ-KID (San Luis)", "Gobierno de San Luis", "San Luis", "Cessna", "Citation V", 2500000, 4800, 750, 1880),
    ("LQ-KJD", "LQ-KJD (La Pampa)", "Gobierno de La Pampa", "La Pampa", "Learjet", "60 XR", 4800000, 5200, 800, 2000),
    ("LQ-KJS", "LQ-KJS (Jujuy)", "Gobierno de Jujuy", "Jujuy", "Beechcraft", "King Air B200", 2800000, 1900, 400, 1000),
    ("LQ-KMA", "LQ-KMA (Corrientes)", "Gobierno de Corrientes", "Corrientes", "Cessna", "Citation V", 2500000, 4800, 750, 1880),
    ("LQ-MRW", "LQ-MRW (Santiago)", "Gobierno de Santiago del Estero", "Santiago del Estero", "Learjet", "45", 3800000, 4500, 700, 1750),
    ("LQ-WKR", "LQ-WKR (Tierra del Fuego)", "Gobierno de Tierra del Fuego", "Tierra del Fuego", "Learjet", "60", 3500000, 5200, 800, 2000),
    ("LQ-WLS", "LQ-WLS (Santa Fe)", "Gobierno de Santa Fe", "Santa Fe", "Learjet", "60", 3500000, 5200, 800, 2000),
    ("LQ-WOL", "LQ-WOL (Misiones)", "Gobierno de Misiones", "Misiones", "Eurocopter", "EC-130", 3200000, 1900, 250, 630),
    ("LQ-WOT", "LQ-WOT (Salta)", "Gobierno de Salta", "Salta", "Learjet", "45 XR", 4200000, 4500, 700, 1750),
    ("LQ-WPD", "LQ-WPD (Buenos Aires)", "Gobierno de Buenos Aires", "Buenos Aires", "Beechcraft", "B-200", 2500000, 1900, 400, 1000),
    ("LQ-WPH", "LQ-WPH (Buenos Aires)", "Gobierno de Buenos Aires", "Buenos Aires", "Learjet", "60", 3500000, 5200, 800, 2000),
    ("LQ-WRE", "LQ-WRE (Mendoza)", "Gobierno de Mendoza", "Mendoza", "Learjet", "60", 3500000, 5200, 800, 2000),
    ("LQ-XRE", "LQ-XRE (Mendoza)", "Gobierno de Mendoza", "Mendoza", "Eurocopter", "EC-145", 6000000, 2800, 350, 880),
    ("LQ-XTC", "LQ-XTC (Neuquen)", "Gobierno de Neuquen", "Neuquen", "Eurocopter", "EC-145", 6000000, 2800, 350, 880),
    ("LQ-YMA", "LQ-YMA (Salta)", "Gobierno de Salta", "Salta", "Eurocopter", "EC-145", 6000000, 2800, 350, 880),
    ("LQ-ZES", "LQ-ZES (Tucuman)", "Gobierno de Tucuman", "Tucuman", "Learjet", "60 XR", 4800000, 5200, 800, 2000),
    ("LQ-ZLS", "LQ-ZLS (Tucuman)", "Gobierno de Tucuman", "Tucuman", "Eurocopter", "AS-350", 2500000, 1800, 220, 550),
    ("LQ-ZPX", "LQ-ZPX (Tucuman)", "Gobierno de Tucuman", "Tucuman", "Beechcraft", "B-200", 2500000, 1900, 400, 1000),
    ("LQ-ZTH", "LQ-ZTH (San Luis)", "Gobierno de San Luis", "San Luis", "Cessna", "Citation V", 2500000, 4800, 750, 1880),
    
    # CONTRATADAS
    ("LV-CCO", "LV-CCO", "Baires Fly", "Contratada", "Bombardier", "Learjet 60", 3500000, 5200, 800, 2000),
    ("LV-CPL", "LV-CPL", "Baires Fly", "Contratada", "Bombardier", "Learjet 60", 2500000, 5200, 800, 2000),
    ("LV-FUF", "LV-FUF", "Baires Fly", "Contratada", "Bombardier", "Learjet 60", 2500000, 5200, 800, 2000),
    ("LV-FVZ", "LV-FVZ", "Baires Fly", "Contratada", "Bombardier", "Learjet 60", 2500000, 5200, 800, 2000),
    ("LV-IYQ", "LV-IYQ", "Baires Fly", "Contratada", "Bombardier", "Learjet 35", 700000, 3800, 650, 1650),
    ("LV-KJY", "LV-KJY (Sanitario SC)", "Gobierno de Santa Cruz", "Santa Cruz", "Pilatus", "PC-24", 14000000, 5000, 600, 1700),
    
    # MILITARES
    ("T-99", "T-99", "Fuerza Aerea Argentina", "Militar", "Boeing", "737-700", 25000000, 12000, 2800, 7100),
    ("TC-61", "TC-61", "Fuerza Aerea Argentina", "Militar", "Lockheed", "C-130H Hercules", 30000000, 15000, 3400, 8500),
]

MATRICULA_TO_ICAO24 = {
    "ARG-01": "e00000", "ARG-02": "e00001", "ARG-03": "e14d34", 
    "ARG-10": "e00002", "ARG-11": "e00003", "ARG-12": "e00004", 
    "LQ-BFS": "e02193", "LQ-CPS": "e03413", "LQ-WOT": "e00015",
    "LV-CCO": "e030cf", "LV-CLK": "e0330b", "LV-CPL": "e0340c", 
    "LV-CTX": "e03518", "LV-FUF": "e06546", "LV-FUK": "e0654b", 
    "LV-FVZ": "e0659a", "LV-GQK": "e0744b", "LV-IYQ": "e09651", 
    "LV-JQF": "e0a446", "LV-JQV": "e0a456", "LV-KFB": "e0b182", 
    "LV-KFL": "e0b18c", "LV-WTV": "e17516", "T-10": "e14c70", 
    "T-33": "e20011", "T-99": "e200ae", "TC-52": "e20004", 
    "TC-61": "e20007", "TC-64": "e20008", "TC-66": "e20094", 
    "TC-70": "e20049",
}

# FIX: No filtramos por e000 ya que son validos para la flota presidencial.
# Solo excluimos si el valor es vacio.
ICAO24_TO_MATRICULA = {v.lower(): k for k, v in MATRICULA_TO_ICAO24.items() if v}
