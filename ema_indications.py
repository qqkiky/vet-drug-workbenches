#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ema_indications.py - EMA 活性成分 -> 英文适应症词库。

EMA/CVMP 检索列表只提供“活性成分”而非完整适应症。为兼顾完整性与严谨性：
- 常用宠物药成分给出规范的英文适应症表述（保守、面向通用场景）；
- 复方按各成分合并；
- 疫苗 / 顺势疗法产品 / 未收录成分使用诚实的中性说明并指向官方标签，
  不编造具体适应症。

用法：enrich_indication(subs_text, product_type) -> str
"""
import re

# --------------------------------------------------------------------------
# canonical: strip salts/solvates so "Amoxicillin trihydrate" -> "amoxicillin"
_SALT_WORDS = (
    "hydrochloride", "dihydrate", "trihydrate", "monohydrate", "sodium",
    "potassium", "calcium", "citrate", "maleate", "besilate", "besylate",
    "sulfate", "sulphate", "phosphate", "tartrate", "embonate", "meglumine",
    "acetate", "hexaacetate", "hydroxide", "dioctyl", "sulphosuccinate",
    "for veterinary use", "concentrate", "powder form", "oily form",
    "synthetic", "liquid", "dil", "aquos",
)

_ALIAS = {
    "clavulanate": "clavulanic acid",
    "potassium clavulanate": "clavulanic acid",
    "amoxicillin trihydrate": "amoxicillin",
    "maropitant citrate": "maropitant",
    "pyrantel embonate": "pyrantel",
    "febantel": "febantel",
    "praziquantel": "praziquantel",
    "milbemycin oxime": "milbemycin oxime",
    "fipronil": "fipronil",
    "imidacloprid": "imidacloprid",
    "methoprene": "(S)-methoprene",
    "s methoprene": "(S)-methoprene",
    "permethrin": "permethrin",
    "flumethrin": "flumethrin",
    "dinotefuran": "dinotefuran",
    "pyriproxyfen": "pyriproxyfen",
    "cefalexin": "cephalexin",
    "cefalexin monohydrate": "cephalexin",
    "metronidazole": "metronidazole",
    "marbofloxacin": "marbofloxacin",
    "enrofloxacin": "enrofloxacin",
    "meloxicam": "meloxicam",
    "carprofen": "carprofen",
    "firocoxib": "firocoxib",
    "robenacoxib": "robenacoxib",
    "ketoprofen": "ketoprofen",
    "flunixin": "flunixin",
    "tol fenamic acid": "tolfenamic acid",
    "tolfenamic acid": "tolfenamic acid",
    "buprenorphine": "buprenorphine",
    "tramadol": "tramadol",
    "butorphanol": "butorphanol",
    "maropitant": "maropitant",
    "pimobendan": "pimobendan",
    "benazepril": "benazepril",
    "imidapril": "imidapril",
    "spironolactone": "spironolactone",
    "torasemide": "torasemide",
    "furosemide": "furosemide",
    "trilostane": "trilostane",
    "thiamazole": "thiamazole",
    "levothyroxine": "levothyroxine",
    "prednisolone": "prednisolone",
    "dexamethasone": "dexamethasone",
    "methylprednisolone": "methylprednisolone",
    "clindamycin": "clindamycin",
    "doxycycline": "doxycycline",
    "oxytetracycline": "oxytetracycline",
    "chlortetracycline": "chlortetracycline",
    "tetracycline": "tetracycline",
    "amoxicillin": "amoxicillin",
    "clavulanic acid": "clavulanic acid",
    "ampicillin": "ampicillin",
    "benzylpenicillin": "benzylpenicillin",
    "procaine": "procaine",
    "penethamate": "penethamate",
    "ceftiofur": "ceftiofur",
    "cephalexin": "cephalexin",
    "cefapirin": "cefapirin",
    "cefquinome": "cefquinome",
    "gentamicin": "gentamicin",
    "neomycin": "neomycin",
    "paromomycin": "paromomycin",
    "kanamycin": "kanamycin",
    "amikacin": "amikacin",
    "tylosin": "tylosin",
    "spiramycin": "spiramycin",
    "lincomycin": "lincomycin",
    "spectinomycin": "spectinomycin",
    "florfenicol": "florfenicol",
    "chloramphenicol": "chloramphenicol",
    "fusidic acid": "fusidic acid",
    "rifaximin": "rifaximin",
    "metronidazole": "metronidazole",
    "sulfadiazine": "sulfadiazine",
    "sulfadoxine": "sulfadoxine",
    "trimethoprim": "trimethoprim",
    "ivermectin": "ivermectin",
    "eprinomectin": "eprinomectin",
    "selamectin": "selamectin",
    "moxidectin": "moxidectin",
    "doramectin": "doramectin",
    "albendazole": "albendazole",
    "fenbendazole": "fenbendazole",
    "flubendazole": "flubendazole",
    "mebendazole": "mebendazole",
    "praziquantel": "praziquantel",
    "pyrantel": "pyrantel",
    "milbemycin": "milbemycin oxime",
    "milbemycin oxime": "milbemycin oxime",
    "emodepside": "emodepside",
    "toltrazuril": "toltrazuril",
    "decoquinate": "decoquinate",
    "clopidol": "clopidol",
    "metergoline": "metergoline",
    "cabergoline": "cabergoline",
    "domperidone": "domperidone",
    "metoclopramide": "metoclopramide",
    "maropitant": "maropitant",
    "atipamezole": "atipamezole",
    "medetomidine": "medetomidine",
    "dexmedetomidine": "dexmedetomidine",
    "xylazine": "xylazine",
    "ketamine": "ketamine",
    "tiletamine": "tiletamine",
    "zolazepam": "zolazepam",
    "acepromazine": "acepromazine",
    "propofol": "propofol",
    "phenobarbital": "phenobarbital",
    "potassium bromide": "potassium bromide",
    "levetiracetam": "levetiracetam",
    "imepitoin": "imepitoin",
    "gabapentin": "gabapentin",
    "ciclosporin": "ciclosporin",
    "oclacitinib": "oclacitinib",
    "lokivetmab": "lokivetmab",
    "miltefosine": "miltefosine",
    "allopurinol": "allopurinol",
    "insulin": "insulin",
    "medroxyprogesterone": "medroxyprogesterone",
    "progesterone": "progesterone",
    "buserelin": "buserelin",
    "gonadorelin": "gonadorelin",
    "deslorelin": "deslorelin",
    "oxytocin": "oxytocin",
    "carbetocin": "carbetocin",
    "dinoprost": "dinoprost",
    "cloprostenol": "cloprostenol",
    "tetracosactide": "tetracosactide",
    "pentosan polysulfate": "pentosan polysulfate",
    "propentofylline": "propentofylline",
    "metamizole": "metamizole",
    "acetylsalicylic acid": "acetylsalicylic acid",
    "lidocaine": "lidocaine",
    "bupivacaine": "bupivacaine",
    "miconazole": "miconazole",
    "ketoconazole": "ketoconazole",
    "itraconazole": "itraconazole",
    "clotrimazole": "clotrimazole",
    "terbinafine": "terbinafine",
    "nystatin": "nystatin",
    "amphotericin": "amphotericin",
    "chlorhexidine": "chlorhexidine",
    "salicylic acid": "salicylic acid",
    "benzoyl peroxide": "benzoyl peroxide",
    "hydrocortisone aceponate": "hydrocortisone aceponate",
    "triamcinolone": "triamcinolone",
    "methyl salicylate": "methyl salicylate",
    "phenylpropanolamine": "phenylpropanolamine",
    "propoxur": "propoxur",
    "fenthion": "fenthion",
    "nitenpyram": "nitenpyram",
    "spinosad": "spinosad",
    "lufenuron": "lufenuron",
    "afoxolaner": "afoxolaner",
    "fluralaner": "fluralaner",
    "sarolaner": "sarolaner",
    "lotilaner": "lotilaner",
    "im idacloprid": "imidacloprid",
    "ciclosp orin": "ciclosporin",
}

# canonical base -> English indication (conservative, generic wording)
IND = {
    "fipronil": "Ectoparasiticide for the control of fleas and ticks on dogs and cats",
    "imidacloprid": "Ectoparasiticide for the control of fleas on dogs and cats",
    "permethrin": "Ectoparasiticide for the control of fleas, ticks, mosquitoes and sand flies on dogs",
    "flumethrin": "Ectoparasiticide (with imidacloprid) for the control of fleas and ticks",
    "dinotefuran": "Ectoparasiticide for the control of fleas on dogs and cats",
    "pyriproxyfen": "Insect growth regulator for the control of flea eggs and immature stages",
    "(s)-methoprene": "Insect growth regulator preventing flea development",
    "methoprene": "Insect growth regulator preventing flea development",
    "ivermectin": "Antiparasitic for the treatment and control of susceptible internal and external parasites",
    "eprinomectin": "Antiparasitic for the treatment and control of susceptible internal and external parasites",
    "selamectin": "Antiparasitic for the prevention of heartworm disease and the control of fleas and other susceptible parasites",
    "moxidectin": "Antiparasitic for the prevention of heartworm disease and the control of susceptible parasites",
    "doramectin": "Antiparasitic for the treatment and control of susceptible internal and external parasites",
    "milbemycin oxime": "Antiparasitic for the prevention of heartworm disease and the control of gastrointestinal nematodes (used alone or with praziquantel)",
    "praziquantel": "Anthelmintic for the treatment of tapeworm infections (used alone or in combination products)",
    "pyrantel": "Anthelmintic for the treatment of roundworm and hookworm infections",
    "febantel": "Anthelmintic for the treatment of roundworm, hookworm and whipworm infections",
    "fenbendazole": "Anthelmintic for the treatment of gastrointestinal nematode infections",
    "albendazole": "Anthelmintic for the treatment of gastrointestinal nematode and tapeworm infections",
    "flubendazole": "Anthelmintic for the treatment of gastrointestinal nematode infections",
    "mebendazole": "Anthelmintic for the treatment of gastrointestinal nematode infections",
    "emodepside": "Anthelmintic for the treatment of gastrointestinal nematode infections",
    "toltrazuril": "Antiprotozoal for the treatment of coccidial infections",
    "decoquinate": "Antiprotozoal for the prevention of coccidial infections",
    "amoxicillin": "Antibiotic for the treatment of infections caused by amoxicillin-susceptible bacteria",
    "clavulanic acid": "Beta-lactamase inhibitor used with amoxicillin to broaden its antibacterial spectrum",
    "tulathromycin": "Macrolide antibiotic for the treatment of susceptible bacterial infections",
    "ampicillin": "Antibiotic for the treatment of infections caused by ampicillin-susceptible bacteria",
    "benzylpenicillin": "Antibiotic for the treatment of infections caused by penicillin-susceptible bacteria",
    "penethamate": "Antibiotic (penicillin) for the treatment of susceptible bacterial infections",
    "ceftiofur": "Cephalosporin antibiotic for the treatment of susceptible bacterial infections",
    "cephalexin": "Cephalosporin antibiotic for the treatment of susceptible bacterial infections, including skin infections",
    "cefapirin": "Cephalosporin antibiotic for the treatment of susceptible bacterial infections, including mastitis",
    "cefquinome": "Cephalosporin antibiotic for the treatment of susceptible bacterial infections",
    "gentamicin": "Aminoglycoside antibiotic for the treatment of susceptible bacterial infections",
    "neomycin": "Aminoglycoside antibiotic for the treatment of susceptible bacterial infections (often in topical/otic preparations)",
    "paromomycin": "Aminoglycoside antibiotic for the treatment of susceptible intestinal infections",
    "tylosin": "Macrolide antibiotic for the treatment of susceptible bacterial infections",
    "spiramycin": "Macrolide antibiotic for the treatment of susceptible bacterial infections",
    "lincomycin": "Lincosamide antibiotic for the treatment of susceptible bacterial infections",
    "spectinomycin": "Aminocyclitol antibiotic for the treatment of susceptible bacterial infections",
    "clindamycin": "Lincosamide antibiotic for the treatment of susceptible bacterial infections, including skin and oral infections",
    "doxycycline": "Tetracycline antibiotic for the treatment of susceptible bacterial infections",
    "oxytetracycline": "Tetracycline antibiotic for the treatment of susceptible bacterial and mycoplasmal infections",
    "chlortetracycline": "Tetracycline antibiotic for the treatment of susceptible bacterial infections",
    "tetracycline": "Tetracycline antibiotic for the treatment of susceptible bacterial infections",
    "florfenicol": "Antibiotic for the treatment of susceptible bacterial infections",
    "chloramphenicol": "Antibiotic for the treatment of susceptible bacterial infections (restricted use)",
    "fusidic acid": "Antibiotic for the treatment of susceptible bacterial skin and eye infections",
    "rifaximin": "Antibiotic for the treatment of susceptible gastrointestinal infections",
    "metronidazole": "Antibiotic/antiprotozoal for the treatment of susceptible anaerobic infections, giardiasis and trichomoniasis",
    "sulfadiazine": "Sulphonamide antibiotic (with trimethoprim) for the treatment of susceptible bacterial infections",
    "sulfadoxine": "Sulphonamide antibiotic (with trimethoprim) for the treatment of susceptible bacterial infections",
    "trimethoprim": "Antibacterial potentiator used with sulphonamides",
    "meloxicam": "NSAID for the relief of pain and inflammation (e.g. musculoskeletal disorders and post-operative pain)",
    "carprofen": "NSAID for the relief of pain and inflammation (e.g. osteoarthritis and post-operative pain)",
    "firocoxib": "COX-2 selective NSAID for the relief of pain and inflammation (e.g. osteoarthritis)",
    "robenacoxib": "COX-2 selective NSAID for the relief of pain and inflammation (e.g. musculoskeletal and post-operative pain)",
    "ketoprofen": "NSAID for the relief of pain and inflammation",
    "flunixin": "NSAID for the relief of pain, inflammation and fever",
    "tol fenamic acid": "NSAID for the relief of pain and inflammation",
    "tolfenamic acid": "NSAID for the relief of pain and inflammation",
    "metamizole": "Analgesic and antipyretic for the relief of pain and fever",
    "acetylsalicylic acid": "Analgesic and antipyretic (aspirin) for the relief of pain and fever",
    "buprenorphine": "Opioid analgesic for the relief of moderate to severe pain",
    "tramadol": "Opioid analgesic for the relief of pain",
    "butorphanol": "Opioid analgesic/sedative for the relief of pain",
    "methadone": "Opioid analgesic for the relief of pain",
    "fentanyl": "Opioid analgesic for the relief of pain",
    "maropitant": "Antiemetic for the prevention and treatment of vomiting (including motion sickness)",
    "domperidone": "Antiemetic/prokinetic used in the management of gastrointestinal motility disorders",
    "metoclopramide": "Antiemetic/prokinetic for the management of nausea, vomiting and gastric motility disorders",
    "pimobendan": "Positive inotrope/vasodilator for the management of congestive heart failure in dogs",
    "benazepril": "ACE inhibitor for the management of heart failure and proteinuric kidney disease",
    "imidapril": "ACE inhibitor for the management of heart failure",
    "spironolactone": "Aldosterone antagonist used with standard therapy for congestive heart failure",
    "torasemide": "Loop diuretic for the management of fluid retention (e.g. heart failure)",
    "furosemide": "Loop diuretic for the management of fluid retention (e.g. heart failure and oedema)",
    "trilostane": "Adrenal steroid synthesis inhibitor for the management of hyperadrenocorticism (Cushing's syndrome)",
    "thiamazole": "Antithyroid agent for the management of hyperthyroidism in cats",
    "levothyroxine": "Thyroid hormone replacement for the management of hypothyroidism in dogs",
    "prednisolone": "Corticosteroid with anti-inflammatory and immunosuppressive activity",
    "dexamethasone": "Corticosteroid with anti-inflammatory and immunosuppressive activity",
    "methylprednisolone": "Corticosteroid with anti-inflammatory and immunosuppressive activity",
    "hydrocortisone aceponate": "Topical corticosteroid for the relief of inflammation and pruritus in dermatoses",
    "triamcinolone": "Corticosteroid with anti-inflammatory activity",
    "ciclosporin": "Immunomodulator for the treatment of atopic dermatitis and immune-mediated conditions",
    "oclacitinib": "JAK inhibitor for the control of pruritus associated with allergic dermatitis",
    "lokivetmab": "Monoclonal antibody for the relief of pruritus associated with allergic dermatitis",
    "miltefosine": "Antiprotozoal for the treatment of leishmaniasis",
    "allopurinol": "Used in the management of leishmaniasis and urate disorders",
    "insulin": "Insulin replacement for the management of diabetes mellitus",
    "medroxyprogesterone": "Progestogen used for oestrus control and certain reproductive/hormonal conditions",
    "progesterone": "Progestogen used in reproductive management",
    "buserelin": "GnRH analogue used in reproductive management (oestrus induction/control)",
    "gonadorelin": "GnRH used in reproductive management",
    "deslorelin": "GnRH agonist implant for reversible contraception in male dogs",
    "oxytocin": "For uterine contraction in obstetric use",
    "carbetocin": "Oxytocin analogue for uterine contraction in obstetric use",
    "dinoprost": "Prostaglandin used for luteolysis and reproductive management",
    "cloprostenol": "Prostaglandin analogue used for luteolysis and reproductive management",
    "tetracosactide": "ACTH analogue used as a diagnostic agent for adrenal function",
    "pentosan polysulfate": "For the management of osteoarthritis (disease-modifying agent)",
    "propentofylline": "Vasodilator/xanthine derivative for the supportive management of cognitive dysfunction and vascular disorders",
    "lidocaine": "Local anaesthetic",
    "bupivacaine": "Local anaesthetic",
    "miconazole": "Antifungal for the treatment of susceptible fungal infections (skin, mucosa)",
    "ketoconazole": "Antifungal for the treatment of susceptible fungal infections",
    "itraconazole": "Antifungal for the treatment of susceptible fungal infections",
    "clotrimazole": "Antifungal for the treatment of susceptible fungal infections",
    "terbinafine": "Antifungal for the treatment of dermatophyte infections",
    "nystatin": "Antifungal for the treatment of candidal infections",
    "chlorhexidine": "Antiseptic/disinfectant for skin and wound care",
    "salicylic acid": "Keratolytic for topical dermatological use",
    "benzoyl peroxide": "Antiseptic/keratolytic for topical dermatological use",
    "methyl salicylate": "Counter-irritant for topical relief in musculoskeletal disorders",
    "phenylpropanolamine": "Sympathomimetic for the management of urethral sphincter incompetence (urinary incontinence) in dogs",
    "propoxur": "Ectoparasiticide (restricted use)",
    "fenthion": "Ectoparasiticide (restricted use)",
    "nitenpyram": "Ectoparasiticide for rapid control of fleas",
    "spinosad": "Ectoparasiticide for the control of fleas",
    "lufenuron": "Insect growth regulator for the control of flea development",
    "afoxolaner": "Ectoparasiticide for the control of fleas and ticks",
    "fluralaner": "Ectoparasiticide for the control of fleas and ticks",
    "sarolaner": "Ectoparasiticide for the control of fleas and ticks",
    "lotilaner": "Ectoparasiticide for the control of fleas and ticks",
    "atipamezole": "Alpha-2 antagonist used to reverse the effects of medetomidine/dexmedetomidine sedation",
    "medetomidine": "Sedative/analgesic (alpha-2 agonist) for sedation and premedication",
    "dexmedetomidine": "Sedative/analgesic (alpha-2 agonist) for sedation and premedication",
    "xylazine": "Sedative/analgesic (alpha-2 agonist)",
    "ketamine": "Dissociative anaesthetic (with sedatives) for anaesthesia",
    "tiletamine": "Dissociative anaesthetic (with zolazepam) for anaesthesia",
    "zolazepam": "Benzodiazepine used with tiletamine for anaesthesia",
    "acepromazine": "Phenothiazine sedative/tranquilliser",
    "phenobarbital": "Antiepileptic for the control of seizures",
    "potassium bromide": "Antiepileptic (adjunct) for the control of seizures",
    "levetiracetam": "Antiepileptic for the control of seizures",
    "imepitoin": "Antiepileptic for the control of seizures in dogs",
    "gabapentin": "Analgesic/antiepileptic (adjunct) for neuropathic pain and seizures",

    "enrofloxacin": "Fluoroquinolone antibiotic for the treatment of susceptible bacterial infections",
    "orbifloxacin": "Fluoroquinolone antibiotic for the treatment of susceptible bacterial infections",
    "pradofloxacin": "Fluoroquinolone antibiotic for the treatment of susceptible bacterial infections",
    "danofloxacin": "Fluoroquinolone antibiotic for the treatment of susceptible bacterial infections",
    "pentobarbital": "Barbiturate used for anaesthesia and controlled euthanasia (veterinary use)",
    "cabergoline": "Dopamine agonist used for the management of hyperprolactinaemia, pseudopregnancy and oestrus induction",
    "deltamethrin": "Ectoparasiticide for the control of fleas and ticks",
    "cloxacillin": "Penicillin antibiotic for the treatment of susceptible bacterial infections (including intramammary use)",
    "dicloxacillin": "Penicillin antibiotic for the treatment of susceptible bacterial infections",
    "nafcillin": "Penicillin antibiotic for the treatment of susceptible bacterial infections",
    "detomidine": "Sedative/analgesic (alpha-2 agonist) for sedation",
    "lactulose": "Osmotic laxative for the management of constipation",
    "chorionic gonadotrophin": "Gonadotrophin for reproductive management",
    "ergometrine": "Ergot alkaloid for uterine contraction (obstetric use)",
    "menbutone": "Choleretic used as supportive therapy in digestive disorders",
    "toldimfos": "Phosphorus-containing tonic used as supportive therapy",
    "prifinium bromide": "Antispasmodic for gastrointestinal spasms",
    "bismuth subnitrate": "Gastrointestinal protectant for supportive therapy of diarrhoea",
    "hyoscine": "Anticholinergic antispasmodic for gastrointestinal spasms",
    "propionic acid": "Preservative/antimicrobial for topical use",
    "boric acid": "Mild antiseptic used in topical preparations",
    "pine tar": "Topical agent for dermatological use",
    "ichthammol": "Topical agent with mild antiseptic/anti-inflammatory properties",
    "copper edta": "Trace-element supplement",
    "zinc edetate": "Trace-element supplement",
    "alpha tocopherol": "Vitamin E supplement",
    "retinol": "Vitamin A supplement",
    "cholecalciferol": "Vitamin D3 supplement",
    "cyanocobalamin": "Vitamin B12 supplement",
    "thiamine": "Vitamin B1 supplement",
    "riboflavin": "Vitamin B2 supplement",
    "folic acid": "Folate supplement",
    "ascorbic acid": "Vitamin C supplement",
    "glucose": "Intravenous fluid/energy supplement for supportive therapy",
    "sodium chloride": "Intravenous fluid/electrolyte for rehydration and supportive therapy",
    "potassium chloride": "Electrolyte for intravenous fluid therapy",
    "calcium gluconate": "Calcium supplement for the management of hypocalcaemia",
    "calcium chloride": "Calcium supplement for intravenous therapy",
    "magnesium chloride": "Magnesium/electrolyte supplement",
    "magnesium sulfate": "Magnesium/electrolyte supplement",
    "magnesium phosphoricum": "Homeopathic/nutritional magnesium preparation",
    "sodium lactate": "Electrolyte/buffer for intravenous fluid therapy",
    "sodium salicylate": "Salicylate with analgesic/anti-inflammatory activity",
    "acetylsalicylic acid": "Analgesic and antipyretic (aspirin) for the relief of pain and fever",
    "potassium bromide": "Antiepileptic (adjunct) for the control of seizures",
    "metamizole": "Analgesic and antipyretic for the relief of pain and fever",
    "chymotrypsin": "Enzyme with anti-inflammatory/debriding activity (topical)",
    "trypsin": "Enzyme with debriding activity (topical)",
    "papain": "Enzyme with debriding activity (topical)",
    "sulfur": "Topical agent for dermatological use",
    "camphor": "Topical counter-irritant",
    "zinc oxide": "Topical protectant for dermatological use",

    "marbofloxacin": "Fluoroquinolone antibiotic for the treatment of susceptible bacterial infections",
    "chlorphenamine": "Antihistamine for the symptomatic relief of allergic reactions and pruritus",
    "metergoline": "Dopamine antagonist used for the management of hyperprolactinaemia and pseudopregnancy",
    "cefovecin": "Cephalosporin antibiotic for the treatment of susceptible bacterial infections",
    "cefadroxil": "Cephalosporin antibiotic for the treatment of susceptible bacterial infections",
    "amoxicillin clavulanic acid": "Broad-spectrum antibiotic (amoxicillin/clavulanic acid) for the treatment of susceptible bacterial infections",
    "pradofloxacin": "Fluoroquinolone antibiotic for the treatment of susceptible bacterial infections",
    "orbifloxacin": "Fluoroquinolone antibiotic for the treatment of susceptible bacterial infections",
    "valnemulin": "Pleuromutilin antibiotic for the treatment of susceptible bacterial infections",
    "coffea": "Homeopathic preparation (EU-registered); refer to the official product labelling",
    "coffea tosta": "Homeopathic preparation (EU-registered); refer to the official product labelling",

    "amlodipine": "Calcium-channel blocker for the management of systemic hypertension in cats (and dogs)",
    "imidocarb": "Antiprotozoal for the treatment of babesiosis",

    "aglepristone": "Antiprogestin used for the termination of pregnancy after mismating in dogs",
}

# --------------------------------------------------------------------------
# matching helpers
# --------------------------------------------------------------------------
_HOMEOPATHY_RE = re.compile(r"(?i)\b([dl])\d{1,4}\b|homaccord|heel\b|ad us\.? vet")

_FLUID_ITEMS = {
    "sodium chloride", "potassium chloride", "calcium chloride",
    "calcium gluconate", "magnesium chloride", "sodium lactate", "glucose",
    "boric acid", "sodium bicarbonate", "magnesium sulfate",
}

_COMBINED_HINTS = [
    # ordered list of (all_must_be_present, text)
    (("amoxicillin", "clavulanic acid"),
     "Broad-spectrum antibiotic (amoxicillin/clavulanic acid) for the treatment of susceptible bacterial infections"),
    (("trimethoprim", "sulfadiazine"),
     "Antibiotic combination (trimethoprim/sulfadiazine) for the treatment of susceptible bacterial infections"),
    (("trimethoprim", "sulfadoxine"),
     "Antibiotic combination (trimethoprim/sulfadoxine) for the treatment of susceptible bacterial infections"),
    (("fipronil", "methoprene"),
     "Ectoparasiticide for the control of fleas and ticks, with an insect growth regulator to prevent reinfestation"),
    (("fipronil", "pyriproxyfen"),
     "Ectoparasiticide for the control of fleas and ticks, with an insect growth regulator to prevent reinfestation"),
    (("imidacloprid", "permethrin"),
     "Ectoparasiticide for the control of fleas, ticks, mosquitoes and sand flies on dogs"),
    (("imidacloprid", "flumethrin"),
     "Ectoparasiticide collar for the control of fleas and ticks on dogs and cats"),
    (("milbemycin oxime", "praziquantel"),
     "Broad-spectrum antiparasitic for the prevention of heartworm disease and the treatment of gastrointestinal nematode and tapeworm infections"),
    (("praziquantel", "pyrantel"),
     "Broad-spectrum anthelmintic for the treatment of tapeworm, roundworm and hookworm infections"),
    (("praziquantel", "febantel", "pyrantel"),
     "Broad-spectrum anthelmintic for the treatment of tapeworm, roundworm, hookworm and whipworm infections"),
    (("praziquantel", "febantel"),
     "Broad-spectrum anthelmintic for the treatment of tapeworm and gastrointestinal nematode infections"),
    (("metronidazole", "spiramycin"),
     "Antibacterial/antiprotozoal combination for the treatment of susceptible infections"),
    (("amoxicillin", "gentamicin"),
     "Antibiotic combination (amoxicillin/gentamicin) for the treatment of susceptible bacterial infections"),
    (("neomycin", "polymyxin"),
     "Antibiotic combination (neomycin/polymyxin) for the treatment of susceptible topical or otic infections"),
    (("miconazole", "polymyxin", "prednisolone"),
     "Combined antifungal/antibacterial/corticosteroid preparation for otitis and dermatoses"),
    (("marbofloxacin", "clotrimazole", "dexamethasone"),
     "Combined antibacterial/antifungal/corticosteroid preparation for otitis externa"),
    (("marbofloxacin", "ketoconazole", "prednisolone"),
     "Combined antibacterial/antifungal/corticosteroid preparation for otitis externa"),
    (("prednisolone", "cefapirin"),
     "Antibiotic/corticosteroid preparation for intramammary use"),
    (("dihydrostreptomycin", "benzylpenicillin"),
     "Antibiotic combination (penicillin/aminoglycoside) for the treatment of susceptible bacterial infections"),
    (("nafcillin", "dihydrostreptomycin", "benzylpenicillin"),
     "Antibiotic combination (penicillin/aminoglycoside) for the treatment of susceptible bacterial infections"),
    (("lincomycin", "neomycin"),
     "Antibiotic combination for the treatment of susceptible bacterial infections"),
    (("spectinomycin", "lincomycin"),
     "Antibiotic combination for the treatment of susceptible bacterial infections"),
    (("decoquinate",),
     "Antiprotozoal for the prevention of coccidial infections"),
]


def _canonical(s: str, strip_salts=True) -> str:
    """Normalise one active-substance string to a lookup key."""
    t = re.sub(r"[\u00b2\u00b3\u2070-\u2079]", " ", str(s))
    t = re.sub(r"[^a-z ]", " ", t.lower())
    t = re.sub(r"\s+", " ", t).strip()
    if strip_salts:
        for w in _SALT_WORDS:
            t = re.sub(r"(^| )" + re.escape(w) + r"($| )", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
    # common aliases
    t = t.replace("s methoprene", "methoprene")
    t = re.sub(r"\bclavulanate\b", "clavulanic acid", t)
    t = re.sub(r"\bamoxicillin clavulanic acid\b", "amoxicillin", t)
    t = re.sub(r"\bsulphadiazine\b", "sulfadiazine", t)
    t = re.sub(r"\bcefalexin\b", "cephalexin", t)
    t = re.sub(r"\bcephalexin\b", "cephalexin", t)
    return t


def _lookup(t: str):
    t = _ALIAS.get(t, t)
    if t in IND:
        return IND[t]
    for k, v in IND.items():
        if k in t:
            return v
    return None


def enrich_indication(subs_text, product_type="Therapeutic"):
    """Build an English indication line from semicolon-separated substances."""
    if not subs_text or not str(subs_text).strip():
        return None
    if _HOMEOPATHY_RE.search(str(subs_text)):
        return ("Homeopathic veterinary medicinal product (EU-registered); "
                "refer to the official product labelling for indications")
    if product_type == "Vaccine":
        return ("Vaccine for active immunisation of the target species; "
                "see the official product labelling for the diseases covered")
    if re.search(r"(?i)\b(virus|strain|vaccin|immunolog|toxoid|antigen|"
                 r"bacterin|serovar|serotype|immunoglobulin)\b", str(subs_text)):
        short = re.sub(r"\s+", " ", str(subs_text)).strip()
        if len(short) > 240:
            short = short[:237].rstrip() + "..."
        return ("Immunological veterinary medicinal product (active "
                "immunisation/passive protection). Active components: %s. "
                "See the official product labelling for the diseases covered."
                % short)
    items = [x.strip() for x in str(subs_text).split(";") if x.strip()]
    cans = []
    for it in items:
        c_full = _canonical(it, strip_salts=False)
        c = c_full if _lookup(c_full) else _canonical(it)
        if c and c not in cans:
            cans.append(c)

    if items and all(
            any(b in _canonical(x, strip_salts=False) for b in _FLUID_ITEMS)
            for x in items):
        return ("Intravenous electrolyte/fluid solution for rehydration and "
                "electrolyte balance (supportive therapy).")

    # combined-product phrases (prefer an explicit combination text)
    for need, txt in _COMBINED_HINTS:
        if all(any(n in c for c in cans) for n in need):
            return txt + "."

    parts = []
    unknown = []
    for c in cans:
        v = _lookup(c)
        if v and v not in parts:
            parts.append(v)
        elif not v:
            unknown.append(c)
    if parts:
        text = "; ".join(dict.fromkeys(parts))
        if unknown:
            text += (" Additional components: %s (see official labelling)."
                     % ", ".join(sorted(set(unknown))))
        return text.rstrip(".") + "."
    if unknown:
        return ("Active substance(s): %s. "
                "Refer to the official product labelling for the authorised "
                "indications." % ", ".join(sorted(set(unknown))))
    return None


if __name__ == "__main__":
    import sys
    for arg in sys.argv[1:]:
        print(arg, "=>", enrich_indication(arg))
