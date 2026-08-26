"""Seed datasets for the Veterinary Biologics Tracking Workbench.

Two snapshots are provided:
  * BASELINE  - an initial full dataset (US USDA/CVB + EU EMA/CVMP).
  * UPDATE    - a *later* snapshot that adds new approvals, withdraws some
                products, and changes status / fields of others, so the
                diff engine has something meaningful to detect.

All records are illustrative/structured samples. Replace with live regulator
feeds via ingest.py for production use.
"""
from copy import deepcopy

# region codes: 'US' (USDA/CVB), 'EU' (EMA/CVMP)
# product_type: 'Vaccine' | 'Diagnostic' | 'Therapeutic'
# species: 'Cat' | 'Dog' | 'Both'

BASELINE = [
    # ---------------- UNITED STATES (USDA / CVB) ----------------
    # Vaccines
    dict(region="US", species="Both", product_type="Vaccine",
         product_name="Defensor 3 Rabies Vaccine", approval_number="CVB-1001",
         manufacturer="Zoetis", indication="Active immunization against rabies",
         dosage_form="Suspension for injection", strength="1 dose / 1 mL",
         approval_date="2020-03-15", status="Active", source="USDA"),
    dict(region="US", species="Dog", product_type="Vaccine",
         product_name="Nobivac DHPPi", approval_number="CVB-1002",
         manufacturer="MSD Animal Health", indication="Canine distemper, adenovirus, parvovirus, parainfluenza",
         dosage_form="Lyophilizate + solvent", strength="1 dose",
         approval_date="2021-06-10", status="Active", source="USDA"),
    dict(region="US", species="Cat", product_type="Vaccine",
         product_name="PUREVAX Rabies", approval_number="CVB-1003",
         manufacturer="Boehringer Ingelheim", indication="Non-adjuvanted rabies immunization in cats",
         dosage_form="Lyophilizate + solvent", strength="1 dose / 1 mL",
         approval_date="2019-09-01", status="Active", source="USDA"),
    dict(region="US", species="Cat", product_type="Vaccine",
         product_name="PUREVAX Feline 3 (FVRCP)", approval_number="CVB-1004",
         manufacturer="Boehringer Ingelheim", indication="Feline viral rhinotracheitis, calicivirus, panleukopenia",
         dosage_form="Lyophilizate + solvent", strength="1 dose",
         approval_date="2019-11-20", status="Active", source="USDA"),
    dict(region="US", species="Dog", product_type="Vaccine",
         product_name="Leptospira Bacterin", approval_number="CVB-1005",
         manufacturer="Zoetis", indication="Leptospirosis caused by L. canicola/grippotyphosa",
         dosage_form="Suspension for injection", strength="1 dose / 1 mL",
         approval_date="2022-01-12", status="Active", source="USDA"),
    dict(region="US", species="Dog", product_type="Vaccine",
         product_name="LymeVax", approval_number="CVB-1006",
         manufacturer="Merck Animal Health", indication="Borrelia burgdorferi (Lyme disease)",
         dosage_form="Suspension for injection", strength="1 dose / 1 mL",
         approval_date="2020-07-08", status="Active", source="USDA"),
    dict(region="US", species="Dog", product_type="Vaccine",
         product_name="BronchiShield Oral Bordetella", approval_number="CVB-1007",
         manufacturer="Zoetis", indication="Bordetella bronchiseptica (kennel cough)",
         dosage_form="Lyophilizate for oral use", strength="1 dose",
         approval_date="2021-02-18", status="Active", source="USDA"),
    dict(region="US", species="Cat", product_type="Vaccine",
         product_name="Leukocell 2 (FeLV)", approval_number="CVB-1008",
         manufacturer="Zoetis", indication="Feline leukemia virus",
         dosage_form="Suspension for injection", strength="1 dose / 1 mL",
         approval_date="2020-05-22", status="Active", source="USDA"),
    dict(region="US", species="Dog", product_type="Vaccine",
         product_name="Canine Influenza H3N8 Vaccine", approval_number="CVB-1009",
         manufacturer="Zoetis", indication="Canine influenza (H3N8)",
         dosage_form="Suspension for injection", strength="1 dose / 1 mL",
         approval_date="2023-04-30", status="Active", source="USDA"),
    dict(region="US", species="Dog", product_type="Vaccine",
         product_name="Puppy DPv", approval_number="CVB-1010",
         manufacturer="Elanco", indication="Canine distemper, parvovirus (puppies)",
         dosage_form="Suspension for injection", strength="1 dose / 1 mL",
         approval_date="2022-09-15", status="Active", source="USDA"),
    dict(region="US", species="Dog", product_type="Vaccine",
         product_name="Vanguard Plus 5 L4", approval_number="CVB-1011",
         manufacturer="Zoetis", indication="DHPP + Leptospira (4 serovars)",
         dosage_form="Lyophilizate + solvent", strength="1 dose",
         approval_date="2022-11-03", status="Active", source="USDA"),
    dict(region="US", species="Cat", product_type="Vaccine",
         product_name="Fel-O-Vax 4 (FVRCP + Chlamy)", approval_number="CVB-1012",
         manufacturer="Boehringer Ingelheim", indication="FVRCP + Chlamydia felis",
         dosage_form="Lyophilizate + solvent", strength="1 dose",
         approval_date="2021-08-14", status="Active", source="USDA"),
    dict(region="US", species="Dog", product_type="Vaccine",
         product_name="Canine Influenza H3N2 Vaccine", approval_number="CVB-1013",
         manufacturer="Zoetis", indication="Canine influenza (H3N2)",
         dosage_form="Suspension for injection", strength="1 dose / 1 mL",
         approval_date="2025-05-20", status="Active", source="USDA"),
    # Diagnostics
    dict(region="US", species="Dog", product_type="Diagnostic",
         product_name="SNAP 4Dx Plus", approval_number="CVB-2001",
         manufacturer="IDEXX", indication="Heartworm + Lyme + Anaplasma + Ehrlichia antibody/antigen",
         dosage_form="Rapid immunoassay kit", strength="5 tests/kit",
         approval_date="2019-03-10", status="Active", source="USDA"),
    dict(region="US", species="Cat", product_type="Diagnostic",
         product_name="SNAP FIV/FeLV Combo", approval_number="CVB-2002",
         manufacturer="IDEXX", indication="Feline immunodeficiency & leukemia virus",
         dosage_form="Rapid immunoassay kit", strength="5 tests/kit",
         approval_date="2020-08-05", status="Active", source="USDA"),
    dict(region="US", species="Dog", product_type="Diagnostic",
         product_name="WITNESS Lepto", approval_number="CVB-2003",
         manufacturer="Zoetis", indication="Detection of Leptospira antibodies",
         dosage_form="Rapid immunoassay kit", strength="10 tests/kit",
         approval_date="2021-12-01", status="Active", source="USDA"),
    dict(region="US", species="Dog", product_type="Diagnostic",
         product_name="SNAP Parvo", approval_number="CVB-2004",
         manufacturer="IDEXX", indication="Canine parvovirus antigen",
         dosage_form="Rapid immunoassay kit", strength="5 tests/kit",
         approval_date="2022-03-19", status="Active", source="USDA"),
    # Therapeutics (biologics)
    dict(region="US", species="Dog", product_type="Therapeutic",
         product_name="Cytopoint (lokivetmab)", approval_number="CVB-3001",
         manufacturer="Zoetis", indication="Control of atopic dermatitis pruritus in dogs",
         dosage_form="Solution for injection", strength="20 mg/mL",
         approval_date="2019-04-12", status="Active", source="USDA"),
    dict(region="US", species="Cat", product_type="Therapeutic",
         product_name="Solensia (frunevetmab)", approval_number="CVB-3002",
         manufacturer="Zoetis", indication="Pain associated with osteoarthritis in cats",
         dosage_form="Solution for injection", strength="5 mg/mL",
         approval_date="2022-01-25", status="Active", source="USDA"),
    dict(region="US", species="Dog", product_type="Therapeutic",
         product_name="Canine Parvovirus Monoclonal Antibody", approval_number="CVB-3003",
         manufacturer="Elanco", indication="Treatment of canine parvovirus",
         dosage_form="Solution for injection", strength="20 mg/mL",
         approval_date="2023-08-14", status="Active", source="USDA"),

    # ---------------- EUROPEAN UNION (EMA / CVMP) ----------------
    # Vaccines
    dict(region="EU", species="Dog", product_type="Vaccine",
         product_name="Rabisin", approval_number="EU/2/19/0101",
         manufacturer="Virbac", indication="Active immunization against rabies",
         dosage_form="Suspension for injection", strength="1 dose / 1 mL",
         approval_date="2019-02-20", status="Active", source="EMA"),
    dict(region="EU", species="Dog", product_type="Vaccine",
         product_name="Duramune DWPPI", approval_number="EU/2/20/0111",
         manufacturer="Ceva", indication="Canine distemper, adenovirus, parvovirus, parainfluenza",
         dosage_form="Lyophilizate + solvent", strength="1 dose",
         approval_date="2020-06-30", status="Active", source="EMA"),
    dict(region="EU", species="Cat", product_type="Vaccine",
         product_name="Feligen RCP", approval_number="EU/2/21/0121",
         manufacturer="Virbac", indication="Feline rhinotracheitis, calicivirus, panleukopenia",
         dosage_form="Lyophilizate + solvent", strength="1 dose",
         approval_date="2021-03-15", status="Active", source="EMA"),
    dict(region="EU", species="Cat", product_type="Vaccine",
         product_name="PUREVAX Rabies", approval_number="EU/2/20/0131",
         manufacturer="Boehringer Ingelheim", indication="Non-adjuvanted rabies immunization in cats",
         dosage_form="Lyophilizate + solvent", strength="1 dose / 1 mL",
         approval_date="2020-10-10", status="Active", source="EMA"),
    dict(region="EU", species="Dog", product_type="Vaccine",
         product_name="Nobivac Lepto", approval_number="EU/2/22/0141",
         manufacturer="MSD Animal Health", indication="Leptospirosis (4 serovars)",
         dosage_form="Lyophilizate + solvent", strength="1 dose",
         approval_date="2022-02-28", status="Active", source="EMA"),
    dict(region="EU", species="Dog", product_type="Vaccine",
         product_name="Canigen Lyme", approval_number="EU/2/21/0151",
         manufacturer="Virbac", indication="Borrelia burgdorferi (Lyme disease)",
         dosage_form="Suspension for injection", strength="1 dose / 1 mL",
         approval_date="2021-07-22", status="Active", source="EMA"),
    dict(region="EU", species="Dog", product_type="Vaccine",
         product_name="BronchiShield (Bordetella)", approval_number="EU/2/23/0161",
         manufacturer="Boehringer Ingelheim", indication="Bordetella bronchiseptica",
         dosage_form="Lyophilizate for oral use", strength="1 dose",
         approval_date="2023-05-09", status="Active", source="EMA"),
    dict(region="EU", species="Cat", product_type="Vaccine",
         product_name="Felocell FeLV", approval_number="EU/2/20/0171",
         manufacturer="Zoetis", indication="Feline leukemia virus",
         dosage_form="Suspension for injection", strength="1 dose / 1 mL",
         approval_date="2020-09-18", status="Active", source="EMA"),
    dict(region="EU", species="Dog", product_type="Vaccine",
         product_name="Eurican DHPPi", approval_number="EU/2/20/0181",
         manufacturer="Boehringer Ingelheim", indication="Canine distemper, adenovirus, parvovirus, parainfluenza",
         dosage_form="Lyophilizate + solvent", strength="1 dose",
         approval_date="2020-12-01", status="Active", source="EMA"),
    dict(region="EU", species="Cat", product_type="Vaccine",
         product_name="PUREVAX FeLV", approval_number="EU/2/21/0191",
         manufacturer="Boehringer Ingelheim", indication="Feline leukemia virus",
         dosage_form="Lyophilizate + solvent", strength="1 dose / 1 mL",
         approval_date="2021-09-09", status="Active", source="EMA"),
    # Diagnostics
    dict(region="EU", species="Dog", product_type="Diagnostic",
         product_name="SNAP 4Dx Plus", approval_number="EU/2/19/0201",
         manufacturer="IDEXX", indication="Heartworm + Lyme + Anaplasma + Ehrlichia",
         dosage_form="Rapid immunoassay kit", strength="5 tests/kit",
         approval_date="2019-05-12", status="Active", source="EMA"),
    dict(region="EU", species="Cat", product_type="Diagnostic",
         product_name="WITNESS FIV/FeLV", approval_number="EU/2/21/0211",
         manufacturer="Zoetis", indication="Feline immunodeficiency & leukemia virus",
         dosage_form="Rapid immunoassay kit", strength="10 tests/kit",
         approval_date="2021-01-30", status="Active", source="EMA"),
    dict(region="EU", species="Dog", product_type="Diagnostic",
         product_name="Anigen Rapid Lepto", approval_number="EU/2/22/0221",
         manufacturer="BioNote", indication="Detection of Leptospira antibodies",
         dosage_form="Rapid immunoassay kit", strength="10 tests/kit",
         approval_date="2022-04-04", status="Active", source="EMA"),
    dict(region="EU", species="Dog", product_type="Diagnostic",
         product_name="VetScan Flex 4", approval_number="EU/2/23/0231",
         manufacturer="Zoetis", indication="Heartworm + Lyme + Anaplasma + Ehrlichia",
         dosage_form="Rapid immunoassay kit", strength="5 tests/kit",
         approval_date="2023-02-11", status="Active", source="EMA"),
    dict(region="EU", species="Dog", product_type="Diagnostic",
         product_name="SNAP Heartworm RT", approval_number="EU/2/25/0202",
         manufacturer="IDEXX", indication="Canine heartworm antigen (rapid)",
         dosage_form="Rapid immunoassay kit", strength="5 tests/kit",
         approval_date="2025-06-11", status="Active", source="EMA"),
    # Therapeutics
    dict(region="EU", species="Dog", product_type="Therapeutic",
         product_name="Cytopoint (lokivetmab)", approval_number="EU/2/19/0301",
         manufacturer="Zoetis", indication="Control of atopic dermatitis pruritus in dogs",
         dosage_form="Solution for injection", strength="20 mg/mL",
         approval_date="2019-06-25", status="Active", source="EMA"),
    dict(region="EU", species="Cat", product_type="Therapeutic",
         product_name="Solensia (frunevetmab)", approval_number="EU/2/22/0311",
         manufacturer="Zoetis", indication="Pain associated with osteoarthritis in cats",
         dosage_form="Solution for injection", strength="5 mg/mL",
         approval_date="2022-03-08", status="Active", source="EMA"),
    dict(region="EU", species="Dog", product_type="Therapeutic",
         product_name="Librela (bedinvetmab)", approval_number="EU/2/23/0321",
         manufacturer="Zoetis", indication="Pain associated with osteoarthritis in dogs",
         dosage_form="Solution for injection", strength="5 mg/mL",
         approval_date="2023-01-16", status="Active", source="EMA"),
]


def get_baseline_dataset():
    return deepcopy(BASELINE)


def get_update_dataset():
    """A later snapshot: adds new approvals, withdraws & modifies some."""
    data = deepcopy(BASELINE)

    # --- Withdraw two products (they disappear from the feed) ---
    data = [r for r in data
            if r["approval_number"] not in ("CVB-1006", "EU/2/21/0151")]

    # --- Status changes ---
    for r in data:
        if r["approval_number"] == "CVB-2003":       # WITNESS Lepto US -> Suspended
            r["status"] = "Suspended"
        if r["approval_number"] == "EU/2/22/0141":    # Nobivac Lepto EU -> Suspended
            r["status"] = "Suspended"

    # --- Field updates ---
    for r in data:
        if r["approval_number"] == "CVB-3001":        # Cytopoint strength changed
            r["strength"] = "30 mg/mL"
        if r["approval_number"] == "EU/2/19/0101":    # Rabisin indication expanded
            r["indication"] = ("Active immunization against rabies (incl. "
                               "booster-free 3-year protocol)")

    # --- New approvals ---
    data.append(dict(region="US", species="Dog", product_type="Therapeutic",
                     product_name="Librela (bedinvetmab)", approval_number="CVB-3004",
                     manufacturer="Zoetis", indication="Pain associated with osteoarthritis in dogs",
                     dosage_form="Solution for injection", strength="5 mg/mL",
                     approval_date="2024-03-12", status="Active", source="USDA"))
    data.append(dict(region="EU", species="Cat", product_type="Vaccine",
                     product_name="Feligen RCPFeLV", approval_number="EU/2/24/0192",
                     manufacturer="Virbac", indication="Feline rhinotracheitis, calicivirus, panleukopenia + FeLV",
                     dosage_form="Lyophilizate + solvent", strength="1 dose",
                     approval_date="2024-01-20", status="Active", source="EMA"))
    data.append(dict(region="US", species="Dog", product_type="Diagnostic",
                     product_name="SNAP Heartworm RT", approval_number="CVB-2005",
                     manufacturer="IDEXX", indication="Canine heartworm antigen (rapid)",
                     dosage_form="Rapid immunoassay kit", strength="5 tests/kit",
                     approval_date="2024-02-09", status="Active", source="USDA"))
    data.append(dict(region="EU", species="Dog", product_type="Therapeutic",
                     product_name="Camlipix mAb (canine atopic)", approval_number="EU/2/25/0331",
                     manufacturer="Ceva", indication="Control of atopic dermatitis pruritus in dogs",
                     dosage_form="Solution for injection", strength="10 mg/mL",
                     approval_date="2025-04-18", status="Active", source="EMA"))
    return data


if __name__ == "__main__":
    print("Baseline products:", len(get_baseline_dataset()))
    print("Update snapshot products:", len(get_update_dataset()))
