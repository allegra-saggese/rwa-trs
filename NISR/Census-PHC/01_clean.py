"""
01_clean.py -- Census: 1_Raw/<year>/Census_<year>.(sav|dta) -> 2_Intermediate/Census_<year>_person_clean.dta

Per census: lower-case names, build the harmonised key block (survey year wave prov dist
sector urban cluster hhid pid sex age wt wt_hh), attach NISR's current province / district /
sector names as value labels, keep every other variable under its own name (2002: English
variable and value labels from the questionnaire, French originals recorded; 2012: NISR recodes
labelled, ISCO-08 titles on P25), record each variable's universe, destring, downcast, back-check, write. Unit = person (public-use 10% household samples; see NISR-Census-PHC.md (decisions log)).
"""
import difflib, sys
import numpy as np, pandas as pd
from census_helpers import (paths, db_root, get_logger, Checks, read_any, write_dta, lower_names,
                            destring, downcast, save_json, LOGS)

log = get_logger("01_clean")
P = paths()
YEARS = [int(a) for a in sys.argv[1:]] or [2002, 2012, 2022]
PUBLISHED_POP = {2002: 8_128_553, 2012: 10_515_973, 2022: 13_246_394}   # NISR published census totals

KEY_ORDER = ["survey", "year", "wave", "prov", "dist", "sector", "urban", "cluster", "hhid", "pid", "sex", "age", "wt", "wt_hh"]
KEY_LABELS = {
    "survey": "Source survey", "year": "Census year", "wave": "Wave (census year)",
    "prov": "Province (1-5, NISR codes)", "dist": "District (11-57, NISR codes)",
    "sector": "Sector (1101-5715, NISR codes; names attached)", "urban": "Area of residence (1 urban, 2 rural)",
    "cluster": "Sampling cluster proxy (year_sector)", "hhid": "Household id (unique within year)",
    "pid": "Person number within the household", "sex": "Sex (1 male, 2 female)", "age": "Age in years",
    "wt": "Person weight (sums to the census population)", "wt_hh": "Household weight (2022 as shipped; 2002/2012 = person weight of the household sample)",
    "pid_nisr": "NISR person number as shipped", "collective": "1 = row belongs to a collective/institutional household (2002 only)",
    "sector_code_file": "Sector code as shipped in the 2002 file (before the name-based correction, see DECISIONS)",
}
URBAN_LABELS = {1: "Urban", 2: "Rural"}

# --- 2002: English variable labels transcribed from the census questionnaire (z_Documentation/2002).
#     Originals (French) are kept in logs/clean_2002_meta.json under var_labels_original.
EN2002 = {
    "province_code": "Province code", "novprov": "Province name", "district_code": "District code (3-digit, as shipped)",
    "novdistr": "District name", "sector_code": "Sector code (5-digit, as shipped)", "novsect": "Sector name",
    "g06_milieu": "Area of residence", "hhid": "Household id", "p00": "Serial number in household roster",
    "p02": "Relationship to household head", "p03": "Residence status (present/absent resident, visitor, collective)",
    "p04": "Sex", "p05x": "Day of birth", "p05a": "Month of birth", "p05b": "Year of birth", "p06": "Age at last birthday",
    "agcm": "Age (NISR derived copy)", "p061": "Age (NISR derived copy 1)", "p062": "Age (NISR derived copy 2)",
    "p063": "Age (NISR derived copy 3)", "p0631": "Age (NISR derived copy 3b)", "age_5": "Age (NISR derived copy, 5)",
    "gpe_age": "Age (NISR derived copy, groups)", "age1_1": "Age (NISR derived copy 1-1)", "a46": "Age (NISR derived copy A46)",
    "age26": "Age (NISR derived copy 26)", "age18": "Age (NISR derived copy 18)", "age19": "Age (NISR derived copy 19)",
    "p07": "Nationality", "p08": "Place of birth (district or country)", "p09": "Duration of residence in this locality (years; 99 since birth)",
    "p10": "Place of previous residence (district or country)", "p11": "Languages spoken", "p12": "Religious affiliation",
    "p13": "Type of major handicap", "personnes_handic": "Persons with a handicap (NISR grouped)", "p14": "Cause of handicap",
    "p15": "Survival of parents", "p16": "School attendance (ever attended)", "fr_quentation": "School attendance (NISR grouped)",
    "p17": "Highest class successfully completed", "p171": "Educational level attained (NISR grouped)",
    "p18": "Area of specialisation (secondary/higher)", "p19": "Highest certificate or diploma obtained", "p20": "Literacy",
    "p21": "Economic activity situation (15/07-15/08/2002)", "p211": "Activity status (NISR grouped)",
    "p22": "Main occupation (type of work done)", "emploi_exerc": "Occupation (NISR grouped)",
    "p23": "Status in employment", "p24": "Branch of economic activity", "p241": "Branch of economic activity (NISR grouped)",
    "p25": "Institutional sector of employment (public/parastatal/NGO/cooperative/other private)",
    "p26": "Marital status", "etat_matri": "Marital status (NISR grouped)",
    "p27a": "Live births ever, boys", "p27b": "Live births ever, girls", "p28a": "Children surviving, boys", "p28b": "Children surviving, girls",
    "p29a": "Births in the last 12 months, boys", "p29b": "Births in the last 12 months, girls",
    "p30a": "Of births in the last 12 months, surviving boys", "p30b": "Of births in the last 12 months, surviving girls",
    "grpage5": "Five-year age group (NISR derived)", "agebetween5_17": "Flag: age 5-17 (NISR derived)", "agegrp_nisr": "Age group (NISR derived, 0-5; shipped as 'Age')",
    "p02_hh": "Flag: household head (P02 = 1)", "h100": "Household type (100 = ordinary household)", "h200": "Collective household type (codes 201-214; not filled)",
    "h101": "Questionnaire serial number in household", "h102": "Number of questionnaires filled in household",
    "h110": "Recap: male residents present", "h111": "Recap: male residents absent", "h112": "Recap: male residents total",
    "h113": "Recap: male residents aged 17+", "h114": "Recap: male visitors", "h115": "Recap: female residents present",
    "h116": "Recap: female residents absent", "h117": "Recap: female residents total", "h118": "Recap: female residents aged 17+",
    "h119": "Recap: female visitors", "h120": "Recap: residents present, total", "h121": "Recap: residents absent, total",
    "h122": "Recap: residents, total", "h123": "Recap: residents aged 17+, total", "h124": "Recap: visitors, total",
    "h01": "Type of housing", "h02": "Type of building", "h03": "Roof material", "h04": "Outer wall material", "h05": "Floor material",
    "h06": "Number of living rooms", "h07": "Main source of water supply", "h08": "Main source of lighting", "h09": "Main cooking energy",
    "h10": "Main toilet facility", "h11": "Main mode of household waste disposal", "h12": "Occupancy status of the dwelling",
    "h13": "Radio / television ownership", "h14": "Fixed-line / cell phone", "h15": "Computer / internet connection",
    "h16a": "Number of vehicles", "h16b": "Number of motorcycles", "h16c": "Number of bicycles", "h17": "Total persons counted in the household",
    "h18": "(empty in the public file)", "h19a": "Any death of a resident member in the last 12 months", "h19b": "Number of deaths in the last 12 months",
    "probability": "Inclusion (selection) probability", "weight": "Final sampling weight", "p00_nu": "NISR artefact: count of P00 in household",
    "p00_mean": "NISR artefact: mean of P00 in household",
}

# --- 2002: English VALUE labels for the key block and the concept variables (relationship, residence,
#     religion, disability, parents, education, literacy, activity, status in employment, institutional
#     sector, marital status, fertility counts, housing block). Transcribed from the 2002 questionnaire
#     (z_Documentation/2002/Census_2002_questionnaire_household.pdf), matched to the French SPSS labels by
#     code. French originals stay in logs/clean_2002_meta.json (value_labels_original). Left in French
#     on purpose (proper names / 3-digit ISCO-88 & ISIC Rev.3 lists not in the English documentation):
#     p08 p10 (pre-2006 districts), p18 (field of study), p22 emploi_exerc (ISCO-88), p24 p241 (ISIC Rev.3).
EN2002_VALUES = {
    "p02": {1: "Head of household", 2: "Spouse of head", 3: "Son/daughter of head", 4: "Unrelated child brought up in the household",
            5: "Father/mother of head", 6: "Brother/sister of head", 7: "Grandchild of head", 8: "Other relative of head", 9: "Non relative (not related to head)"},
    #   wording aligned with the 2012 list (same nine categories) so the version rule keeps 2002 and 2012 in one column
    "p03": {1: "Present resident", 2: "Absent resident", 3: "Visitor", 4: "Collective household", 9: "Not stated"},
    "p05a": {1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June", 7: "July", 8: "August", 9: "September",
             10: "October", 11: "November", 12: "December", 99: "Month of birth not stated"},
    "p05b": {9999: "Year of birth not stated"},
    "p07": {100: "Rwanda", 201: "Burundi", 202: "DR Congo (Congo-Kinshasa)", 203: "Uganda", 204: "Tanzania", 207: "Belgium", 212: "India"},
    "p12": {1: "Catholic", 2: "Protestant", 3: "Adventist", 4: "Jehovah's Witness", 5: "Other Christian religion", 6: "Muslim",
            7: "Traditional/animist", 8: "Other religion", 9: "No religion"},
    "p13": {1: "No major handicap", 2: "Blind", 3: "Deaf/dumb", 4: "Infirmity of the legs/feet", 5: "Infirmity of the arms/hands",
            6: "Mental deficiency", 7: "Trauma", 8: "Other major handicap"},
    "p14": {1: "Congenital", 2: "Illness", 3: "Accident", 4: "War", 5: "Genocide", 6: "Mines", 7: "Other", 8: "Don't know"},
    "p15": {1: "Both parents alive", 2: "Mother only alive", 3: "Father only alive", 4: "Neither alive"},
    "p16": {1: "Attending / attended school", 2: "Never went to school"}, "fr_quentation": {1: "Attending / attended school"},
    "p17": {99: "Not stated"}, "p171": {99: "Not stated"},
    "p19": {1: "None", 2: "EMA: primary teacher training or equivalent", 3: "A3/D4/D5: secondary teacher training or equivalent",
            4: "A2/D6/D7: diploma of humanities or equivalent", 5: "A1: baccalaureat, GCE A level or equivalent",
            6: "A0: BA, maitrise, ingeniorat or equivalent", 7: ">A0: MA, doctorate", 9: "Not stated"},
    "p20": {1: "Can read and write", 2: "Can read only", 3: "Cannot read or write"},
    "p21": {1: "Employed", 2: "Temporarily unemployed", 3: "First job seeker", 4: "Unpaid homekeeper", 5: "Pupil/student",
            6: "Retired", 7: "Elderly landowner/landlord (rentier)", 8: "Jobless / has no work"},
    "p23": {1: "Self-employed", 2: "Employer", 3: "Regularly paid worker", 4: "Temporarily paid worker", 5: "Apprentice",
            6: "Unpaid family worker", 7: "Other"},
    "p25": {1: "Public", 2: "Parastatal", 3: "NGO", 4: "Cooperative", 5: "Other private", 9: "Not stated"},
    "p26": {1: "Never married (bachelor/spinster)", 2: "Cohabitation / common-law union", 3: "Monogamous marriage",
            4: "Polygamous married man", 5: "First wife in a polygamous marriage", 6: "Second wife in a polygamous marriage",
            7: "Third or later wife in a polygamous marriage", 8: "Divorced/separated", 9: "Widowed"},
    "etat_matri": {1: "Never married", 8: "Divorced/separated", 9: "Widowed", 99: "Not stated"},
    "h100": {100: "Ordinary household"},
    "h200": {201: "Police camp", 202: "Home for old persons", 203: "Military camp", 204: "Religious institution", 205: "Street children",
             206: "Schools", 207: "Prison", 208: "Reception centre", 209: "Hotel/lodging", 210: "Centre for disabled, deaf and dumb",
             211: "Hospital", 212: "Orphanage", 213: "Refugee camp", 214: "Youth centre"},
    "h01": {1: "Umudugudu (new rural agglomeration)", 2: "Old settlement (early rural agglomeration)", 3: "Dispersed/isolated housing",
            4: "Planned urban housing (cadastral plot)", 5: "Spontaneous/squatter housing", 6: "Other type of housing", 9: "Not stated"},
    "h02": {1: "Building occupied by one household", 2: "Building occupied by several households",
            3: "Storey building occupied by one or more households", 4: "Several buildings in a compound occupied by several households",
            5: "Other type of building", 9: "Not stated"},
    "h03": {1: "Zinc / iron sheets", 2: "Local tiles", 3: "Industrial tiles/slates", 4: "Concrete", 5: "Cartons/sheeting", 6: "Grass/straw", 7: "Other", 9: "Not stated"},
    "h04": {1: "Wood / unplastered mud walls", 2: "Wood / cemented mud walls", 3: "Sun-dried (adobe) bricks", 4: "Burnt bricks",
            5: "Cement blocks / concrete", 6: "Stone", 7: "Planks", 8: "Plastic sheeting / cartons", 9: "Other", 99: "Not stated"},
    "h05": {1: "Earth", 2: "Cement", 3: "Stone", 4: "Floor tiles", 5: "Burnt bricks", 6: "Other", 9: "Not stated"},
    "h07": {1: "Internal pipe-borne water", 2: "Pipe-borne water in the compound", 3: "Public tap outside the compound",
            4: "Protected spring/well", 5: "Unprotected spring/well", 6: "Rain water", 7: "River", 8: "Lake/stream/pond/surface water", 9: "Other", 99: "Not stated"},
    "h08": {1: "Electricity (Electrogaz)", 2: "Hydro-electric or other private source", 3: "Solar panel / electric generator",
            4: "Kerosene lamp", 5: "Oil lamp", 6: "Candle", 7: "Firewood", 8: "Other", 9: "Not stated"},
    "h09": {1: "Electricity", 2: "Gas", 3: "Kerosene", 4: "Firewood", 5: "Charcoal", 6: "Vegetal material (grass, leaves)", 7: "Other", 9: "Not stated"},
    "h10": {1: "Flush toilet (WC)", 2: "Private pit latrine", 3: "Public/shared pit latrine", 4: "Bush", 5: "Other", 9: "Not stated"},
    "h11": {1: "Compost dumping", 2: "Private dust bin", 3: "Public refuse dump", 4: "In the bush", 5: "On the farm", 6: "In a river/stream/drain", 7: "Other", 9: "Not stated"},
    "h12": {1: "Owner", 2: "Tenant", 3: "Hire purchase", 4: "Free lodging", 5: "Service housing", 6: "Refuge / temporary camp", 7: "Other", 9: "Not stated"},
    "h13": {1: "Radio", 2: "Television", 3: "Radio and television", 4: "None", 9: "Not stated"},
    "h14": {1: "Fixed-line telephone", 2: "Cell phone", 3: "Fixed-line and cell phone", 4: "None", 9: "Not stated"},
    "h15": {1: "Computer", 2: "Computer and internet connection", 3: "None", 9: "Not stated"},
    "h19a": {1: "Yes", 2: "No", 9: "Not stated"},
}
for _v in ("p29a", "p29b", "p30a", "p30b"):
    EN2002_VALUES[_v] = {0: "None", 1: "1 birth", 2: "2 births", 3: "3 births", 4: "4 births", 9: "Not stated"}
EN2002_VALUES["h16a"] = {0: "No vehicle", **{k: f"{k} vehicle{'s' if k > 1 else ''}" for k in range(1, 5)}, 9: "Not stated"}
EN2002_VALUES["h16b"] = {0: "No motorcycle", **{k: f"{k} motorcycle{'s' if k > 1 else ''}" for k in range(1, 9)}, 9: "Not stated"}
# whole-label phrases that recur across the remaining 2002 variables
FR_PHRASES = {"non déterminé": "Not stated", "nd": "Not stated", "aucun": "None", "autre": "Other", "autres": "Other", "oui": "Yes", "non": "No",
              "not applicable": "Not applicable"}
# p11 (languages spoken) is a coded combination; tokens are joined with ' + '
LANG_TOKENS = {"Muet": "Mute (no language)", "Kinyarwanda": "Kinyarwanda", "Kiny": "Kinyarwanda", "Français": "French", "Fran": "French",
               "Swahili": "Swahili", "Swah": "Swahili", "Anglais": "English", "Angl": "English", "Ang": "English",
               "Autres langues": "Other languages", "Autr": "Other"}

def translate_2002_values(vv, log):
    """Replace French value-label text by the English transcription, code by code; returns the set of
    variables touched. Codes not covered by the transcription keep their French text."""
    done = set()
    for var, d in vv.items():
        if not isinstance(d, dict): continue
        new, hit = {}, 0
        for k, txt in d.items():
            try: code = int(float(k))
            except (TypeError, ValueError): new[k] = txt; continue
            if var in EN2002_VALUES and code in EN2002_VALUES[var]: new[k] = EN2002_VALUES[var][code]; hit += 1
            elif var == "p11": new[k] = " + ".join(LANG_TOKENS.get(t.strip(), t.strip()) for t in str(txt).split("+")); hit += 1
            elif str(txt).strip().lower() in FR_PHRASES: new[k] = FR_PHRASES[str(txt).strip().lower()]; hit += 1
            else: new[k] = txt
        if var in EN2002_VALUES:   # codes defined in the questionnaire but absent from the SPSS label set (e.g. P13 = 1)
            for code, txt in EN2002_VALUES[var].items():
                if code not in {int(float(k)) for k in new if str(k).replace('.', '').lstrip('-').isdigit()}: new[code] = txt; hit += 1
        if hit: vv[var] = new; done.add(var)
    log.info("2002 value labels translated to English for %d variables: %s", len(done), " ".join(sorted(done)))
    return done

# --- 2012: NISR's recoded variables ship with their name as the only label; documented from the
#     questionnaire, the edit specifications and the thematic reports (see NISR-Census-PHC.md (documentation notes)) and
#     verified against the source variables in the data (cross-tabulations in NISR-Census-PHC.md (decisions log)).
RP2012_LABELS = {
    "rp142": "Parental co-residence, residents under 18 (NISR recode of P14b x P14d)",
    "rp12": "Disability status, any difficulty (NISR recode of P12)",
    "rp08": "Nationality group (NISR recode of P08)",
    "rp2024": "Activity status, residents aged 5+ (NISR recode of P20-P24; 1 = worked or on leave, 2/3 = did not work and available, 4-7 inactive)",
    "rp2124": "Reason for not working (NISR recode of P21, inactive only)",
    "rl07": "Urban/rural, 2-way (NISR recode of L07: urban + semi-urban = 1, rural + peri-urban = 2)",
    "rp04y": "Year of birth (NISR copy of P04Y)",
    "p25": "Main occupation, ISCO-08 4-digit (labels from z_Documentation/2012 ISCO code list; 1-digit groups in rp25)",
    "p27": "Branch of economic activity, ISIC Rev.4 class (3-4 digit code as shipped, unlabelled by NISR; sections in rp27)",
}

def isco08_labels(log):
    """ISCO-08 unit-group (4-digit) titles from NISR's 2012 coding list (z_Documentation/2012/Census_2012_rhpc_isco_codes.xls)."""
    x = pd.read_excel(P["root"] / "z_Documentation" / "2012" / "Census_2012_rhpc_isco_codes.xls", sheet_name="ISCO", header=None)
    lab = {}
    for _, r in x.iterrows():
        code, title = r[3], r[5]
        if pd.notna(code) and isinstance(code, (int, float)) and 1000 <= int(code) <= 9999 and isinstance(title, str) and title.strip():
            lab[int(code)] = title.strip()
    log.info("ISCO-08 list: %d unit groups", len(lab))
    return lab

# --- Universe (who was asked) per variable and year, from the questionnaires; written to the meta
#     files and shown in the codebook. Patterns are regexes on the lower-cased variable name.
UNIVERSE = {
    2002: [(r"^(p07|p08|p09|p10|p11|p12|p13)$", "residents (P03 = 1, 2); visitors skip to next person"),
           (r"^p14$", "persons with a major handicap (P13 != 1)"), (r"^p15$", "persons aged 25 or less"),
           (r"^(p16|fr_quentation|p17|p171|p18|p19|p20)$", "population aged 6+ (P18/P19 if attended school)"),
           (r"^(p21|p211)$", "population aged 6+"), (r"^(p22|emploi_exerc|p23|p24|p241|p25)$", "economically active aged 6+ (P21 = 1 employed or 2 temporarily unemployed)"),
           (r"^(p26|etat_matri)$", "residents aged 12+"), (r"^(p27|p28|p29|p30)[ab]$", "resident women aged 12+"),
           (r"^h(0\d|1\d[abc]?|19[ab])$", "ordinary (private) households"), (r"^p05[xab]$", "all persons (day of birth not asked; NISR field)")],
    2012: [(r"^(p07|p08|p09|p10)$", "usual residents"), (r"^p14[abcd]$", "residents under 18"), (r"^p15$", "all residents (birth registration)"),
           (r"^(p16|p17|p18a|p18b|p19)$", "residents aged 3+ (P18a-P19 if ever attended school)"),
           (r"^(p20|p21|p22|p23|p24|rp2024|rp2124)$", "residents aged 5+ (P21-P24 only if did not work in the last 7 days)"),
           (r"^(p25|p26|p27|p28|rp25|rp27)$", "residents aged 5+ currently working or who ever worked"),
           (r"^(p29)$", "residents aged 12+"), (r"^p30$", "married men aged 12+"), (r"^p31$", "married women aged 12+"), (r"^p32$", "ever-married residents aged 12+"),
           (r"^p3[3456][mf]$", "resident women aged 12+"), (r"^h\d", "private households (repeated on every member)"), (r"^m1$", "private households (deaths in the last 12 months)")],
    2022: [(r"^p06$", "residents aged 12+"), (r"^p08[abc]$", "residents aged 12+ in a union (P08a men, P08b women in polygamous union)"),
           (r"^(p09[abc]|p10[ab]|p11[ab]|p12b|p13|p14)$", "usual residents"), (r"^p(1[5-9]|2[012])[ab]*$", "residents aged 5+ (disability, Washington Group)"),
           (r"^p2[34]", "residents under 18"), (r"^p2[5-8]", "residents aged 18+ (and under-18s without registered birth)"),
           (r"^(p29|p30[ab]|p31)$", "all residents (P30-P31 if ever attended school)"), (r"^(p32|p33)$", "residents aged 10+"),
           (r"^(p34|p35|p36c)$", "residents aged 10+"), (r"^(p46|p47a|p48a|p49)$", "employed residents aged 16+ (P37-P45 identification questions are not in the public file)"),
           (r"^p5[01]", "resident women aged 10+"), (r"^h\d", "private households (repeated on every member)")],
}
def universe_for(y, cols):
    import re
    out = {}
    for c in cols:
        for pat, txt in UNIVERSE.get(y, []):
            if re.match(pat, c): out[c] = txt; break
    return out

# --- NISR current administrative names (geodata-nisr village file) -> value labels for prov/dist/sector
geo = db_root() / "geodata-nisr" / "Village_Boundary_2022_924768113126413998.csv"
v = pd.read_csv(geo)
SECTORS = v.drop_duplicates("Sector ID")[["Province ID", "Province", "District ID", "District", "Sector ID", "Sector"]].sort_values("Sector ID")
PROV_LABELS = {int(k): s for k, s in SECTORS.drop_duplicates("Province ID")[["Province ID", "Province"]].values}
DIST_LABELS = {int(k): s for k, s in SECTORS.drop_duplicates("District ID")[["District ID", "District"]].values}
SECT_LABELS = {int(k): s for k, s in SECTORS[["Sector ID", "Sector"]].values}
assert len(SECT_LABELS) == 416 and len(DIST_LABELS) == 30 and len(PROV_LABELS) == 5

def sector_by_name_2002(df, log, ck):
    """Assign the current NISR sector code to each 2002 sector by NAME within district (the
    shipped codes are permuted in Musanze 4301-4304 and spelt with R/L variants elsewhere)."""
    tab = df[["sector_code_file", "novsect", "dist"]].drop_duplicates("sector_code_file")
    mapping, changed = {}, []
    for d, grp in tab.groupby("dist"):
        cand = SECTORS[SECTORS["District ID"] == d]
        names = {s.strip().upper(): int(k) for k, s in cand[["Sector ID", "Sector"]].values}
        left = dict(names)
        pend = []
        for code, nm in grp[["sector_code_file", "novsect"]].values:
            key = str(nm).strip().upper()
            if key in left: mapping[code] = left.pop(key)
            else: pend.append((code, key))
        for code, key in pend:   # spelling variants: closest remaining name in the same district
            m = difflib.get_close_matches(key, list(left), n=1, cutoff=0.6)
            if not m: raise ValueError(f"2002 sector {key} ({code}) in district {d} has no match among {list(left)}")
            mapping[code] = left.pop(m[0]); log.info("2002 sector name %-14s matched to %-14s (%s)", key, m[0], mapping[code])
    out = df["sector_code_file"].map(mapping)
    shipped = (df["sector_code_file"] // 10000) * 1000 + ((df["sector_code_file"] % 10000) // 100) * 100 + df["sector_code_file"] % 100
    for code, new in mapping.items():
        old = int((code // 10000) * 1000 + ((code % 10000) // 100) * 100 + code % 100)
        if old != new: changed.append((int(code), old, new, SECT_LABELS[new]))
    log.info("2002 sectors whose code changed after name matching: %s", changed)
    ck(len(set(mapping.values())) == 416, "2002: 416 distinct sectors after name matching")
    ck((out // 100 == df["dist"]).all(), "2002: corrected sector code nests in district")
    return out, shipped

def ren(df, vl, vv, src, dst, srcmap):
    if src in df.columns and dst not in df.columns:
        df.rename(columns={src: dst}, inplace=True)
        if src in vl: vl[dst] = vl.pop(src)
        if src in vv: vv[dst] = vv.pop(src)
        srcmap[dst] = src; return True
    return False

for y in YEARS:
    log.info("---------------- %s ----------------", y)
    raw = P["raw"] / str(y) / (f"Census_{y}.sav" if y == 2002 else f"Census_{y}.dta")
    df, vl, vv = read_any(raw)
    n_raw = len(df); log.info("read %s: %s rows x %s vars", raw.name, f"{n_raw:,}", df.shape[1])
    df, vl, vv = lower_names(df, vl, vv, log)
    srcmap, ck = {}, Checks(log)
    df["survey"] = "Census"; df["year"] = np.int16(y); df["wave"] = str(y)
    vl_original, vv_original = None, {}

    if y == 2002:
        df = df.rename(columns={"age": "agegrp_nisr"}); vl["agegrp_nisr"] = vl.pop("age", ""); vv.pop("age", None)   # free the name for P06
        vl_original = dict(vl)
        for c, t in EN2002.items():
            if c in df.columns: vl[c] = t
        missing = [c for c in df.columns if c not in EN2002 and c not in ("survey", "year", "wave")]
        ck(not missing, f"2002: every variable has an English label ({missing})", hard=False)
        vv_original = {k: dict(v) for k, v in vv.items() if isinstance(v, dict)}
        translated = translate_2002_values(vv, log)
        ck({"p02", "p03", "p21", "p23", "p26", "p19", "p20"} <= translated, "2002: concept variables carry English value labels")
        ren(df, vl, vv, "province_code", "prov", srcmap)
        df["dist"] = (df["district_code"] // 100) * 10 + df["district_code"] % 100; srcmap["dist"] = "district_code (3-digit prov*100+seq -> prov*10+seq)"
        df = df.rename(columns={"sector_code": "sector_code_file"}); vl["sector_code_file"] = KEY_LABELS["sector_code_file"]
        df["sector"], _ = sector_by_name_2002(df, log, ck); srcmap["sector"] = "novsect matched by name to NISR current sector codes (sector_code_file kept)"
        ren(df, vl, vv, "g06_milieu", "urban", srcmap)
        df["pid_nisr"] = df["p00"]; df = df.drop(columns=["p00"])
        df["pid"] = df.groupby("hhid").cumcount() + 1; srcmap["pid"] = "row order within household (P00 is not unique within households; kept as pid_nisr)"
        ren(df, vl, vv, "p04", "sex", srcmap); ren(df, vl, vv, "p06", "age", srcmap)
        ren(df, vl, vv, "weight", "wt", srcmap); df["wt_hh"] = df["wt"]; srcmap["wt_hh"] = "= wt (10% household sample, self-weighting)"
        df["collective"] = (df["h100"].isna()).astype("int8"); srcmap["collective"] = "h100 missing: collective/institutional household rows (no household id, no H-block; P03 is 1 on all of them)"
        vv["sex"] = {1: "Male", 2: "Female"}
    elif y == 2012:
        ren(df, vl, vv, "l01", "prov", srcmap); ren(df, vl, vv, "dui", "dist", srcmap); ren(df, vl, vv, "sui", "sector", srcmap)
        # l07 has 4 categories (urban 13.9%, rural 75.3%, peri-urban 8.5%, semi-urban 2.3%, weighted). NISR's own
        # 2-way recode rl07 counts semi-urban as urban and peri-urban as rural (verified: rl07 = 1 <=> l07 in {1, 4});
        # it reproduces the published 2012 urban share (16.5%; 16.2% in the sample) where l07 == 1 alone gives 13.9%.
        # key-block urban therefore = rl07; l07 is carried untouched.
        ck(bool(((df["rl07"] == 1) == df["l07"].isin([1, 4])).all()), "2012: rl07 == 1 <=> l07 in {urban, semi-urban}")
        df["urban"] = df["rl07"]; srcmap["urban"] = "rl07 (NISR 2-way recode: urban + semi-urban = 1, rural + peri-urban = 2; l07 kept)"
        for c, t in RP2012_LABELS.items():
            if c in df.columns: vl[c] = t
        isco = isco08_labels(log)
        codes = set(int(x) for x in df["p25"].dropna().unique()); unmatched = sorted(codes - set(isco))
        log.info("2012 P25: %d distinct ISCO codes, %d not in the list: %s", len(codes), len(unmatched), unmatched[:20])
        ck(len(unmatched) <= 0.02 * len(codes), f"2012: >= 98% of P25 codes found in the ISCO-08 list ({len(unmatched)} unmatched)", hard=False)
        # 9999 = invalid code imputed by NISR's edit program (edit specs P25SPEC26); 9998 = not stated (NISR sentinel)
        vv["p25"] = {k: v for k, v in isco.items() if k in codes} | {9998: "Not stated", 9999: "Invalid code (NISR edit imputation)"} | {k: "ISCO code not in the 2012 list" for k in unmatched if k not in (9998, 9999)}
        vv["rp2024"] = dict(vv.get("rp2024", {})) | {9: "Not classified (code unlabelled by NISR: P21 = home worker / never worked / other)"}
        ren(df, vl, vv, "p01", "pid", srcmap); ren(df, vl, vv, "p03", "sex", srcmap); ren(df, vl, vv, "p05", "age", srcmap)
        ren(df, vl, vv, "sampleweight_final_", "wt", srcmap); df["wt_hh"] = df["wt"]; srcmap["wt_hh"] = "= wt (10% household sample, self-weighting)"
    else:
        ren(df, vl, vv, "ml01", "prov", srcmap); ren(df, vl, vv, "ml02", "dist", srcmap); ren(df, vl, vv, "ml03", "sector", srcmap)
        ren(df, vl, vv, "ml07", "urban", srcmap)
        ren(df, vl, vv, "p01", "pid", srcmap); ren(df, vl, vv, "p03", "sex", srcmap); ren(df, vl, vv, "p04", "age", srcmap)
        ren(df, vl, vv, "pop_weight", "wt", srcmap); ren(df, vl, vv, "hh_weight", "wt_hh", srcmap)
    df["cluster"] = df["year"].astype(str) + "_" + df["sector"].astype("Int64").astype(str)
    df["hhid"] = df["hhid"].astype("Int64")            # nullable: 2002 collective-household rows carry no hhid
    log.info("rows without a household id: %s", f"{int(df['hhid'].isna().sum()):,}")
    vv["prov"], vv["dist"], vv["sector"], vv["urban"] = PROV_LABELS, DIST_LABELS, SECT_LABELS, URBAN_LABELS
    for c, t in KEY_LABELS.items():
        if c in df.columns: vl[c] = t

    df = destring(df, log, skip=("survey", "wave", "cluster", "novprov", "novdistr", "novsect"))
    df = downcast(df, keep_double=("wt", "wt_hh", "hhid", "probability"))
    df = df[KEY_ORDER + [c for c in df.columns if c not in KEY_ORDER]]

    # ---- back-checks
    ck(len(df) == n_raw, f"row count unchanged ({n_raw:,})")
    ck(df["wt"].notna().all() and (df["wt"] > 0).all(), "wt present and > 0 on every row")
    ck(df["prov"].nunique() == 5 and df["dist"].nunique() == 30 and df["sector"].nunique() == 416, "5 provinces / 30 districts / 416 sectors")
    ck(set(df["sector"].unique()) == set(SECT_LABELS), "sector codes == NISR current 416-sector list")
    ck((df["sector"] // 100 == df["dist"]).all() and (df["dist"] // 10 == df["prov"]).all(), "sector nests in district nests in province")
    ck(set(df["sex"].dropna().unique()) <= {1, 2}, "sex in {1,2}")
    ck(df["age"].between(0, 130).all(), f"age in [0,130] (max {df['age'].max()})")
    ordinary = df if "collective" not in df.columns else df[df["collective"] == 0]
    heads = ordinary.groupby("hhid")["p02"].apply(lambda s: int((s == 1).sum()))
    ck(heads.eq(1).all(), f"exactly one head per (ordinary) household: {heads.eq(1).mean():.4%} of {len(heads):,}")
    ck(not df[df["hhid"].notna()].duplicated(["hhid", "pid"]).any(), "(hhid, pid) unique")
    ck((df.groupby("hhid")["wt_hh"].nunique() <= 1).all(), "wt_hh constant within household")
    ck((df.groupby("hhid")[["prov", "dist", "sector"]].nunique() <= 1).all().all(), "prov/dist/sector constant within household")
    n_urb = int((df.groupby("hhid")["urban"].nunique(dropna=False) > 1).sum())
    ck(n_urb == 0, f"urban constant within household ({n_urb} households differ; NISR data as shipped -- the household file takes the head's value, 02_merge)", hard=False)
    if "collective" in df.columns:   # structural test: collective rows are exactly the rows without a household id (they carry no H-block either)
        ck(bool(((df["collective"] == 1) == df["hhid"].isna()).all()), f"collective flag == rows without a household id ({int((df['collective'] == 1).sum()):,} rows)")
    tot = df["wt"].sum(); pub = PUBLISHED_POP[y]
    ck(abs(tot / pub - 1) < 0.02, f"weighted population {tot:,.0f} within 2% of published {pub:,} ({tot / pub - 1:+.2%})")
    if "hhsize" in df.columns:
        ck((df.groupby("hhid").size() == df.groupby("hhid")["hhsize"].first()).all(), "shipped hhsize == roster count")
    log.info("households: %s | urban share (weighted): %.3f", f"{df['hhid'].nunique():,}", (df["wt"] * (df["urban"] == 1)).sum() / tot)
    ck.done()

    out = P["inter"] / f"Census_{y}_person_clean.dta"
    write_dta(df, out, vl, vv, f"Rwanda Census {y} person file (public-use sample, cleaned)", log)
    meta = {"n": len(df), "vars": list(df.columns), "var_labels": vl, "value_labels": {k: v for k, v in vv.items() if k in df.columns},
            "source": srcmap, "dtypes": {c: str(df[c].dtype) for c in df.columns}}
    if vl_original: meta["var_labels_original"] = vl_original
    if y == 2002: meta["value_labels_original"] = {k: v for k, v in vv_original.items() if k in df.columns}
    meta["universe"] = universe_for(y, df.columns)
    save_json(meta, LOGS / f"clean_{y}_meta.json")
log.info("01_clean done for %s", YEARS)
