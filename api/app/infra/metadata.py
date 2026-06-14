from ui.components import diagnostic_handler

# Metadata Standard Schemas (INE and SECTRA)
CHILEAN_SCHEMAS = {
    "INE_CENSO_2024": {
        "pop_total": ["pop_h3", "PERSONAS", "TOTAL_PERS", "CANT_PERS", "n_per"],
        "age_0_14": ["P01_1", "EDAD_0_14"],
        "age_65_plus": ["P01_3", "EDAD_65_MAS"],
        "households": ["HOGARES", "TOTAL_HOG"],
        "geometry": ["geometry", "geom", "SHAPE"]
    },
    "SECTRA_EOD": {
        "trips": ["trips", "VIAJES", "n_viajes", "Viajes_Totales"],
        "expansion_factor": ["Factor_Expansion", "FACTOR", "FACTOR_EXPANSION", "factor_exp"],
        "purpose": ["Proposito", "PROPOSITO_VIAJE"],
        "mode": ["Modo", "MODO_TRANSPORTE"],
        "h3_origin": ["h3_origin", "ORIGEN_H3", "Zona_Origen"],
        "h3_dest": ["h3_dest", "h3_destination", "DESTINO_H3", "Zona_Destino"]
    }
}

# HYGIENIC INVARIANTS: Columns that MUST exist for the engine to function.
INDISPENSABLE_COLUMNS = {
    "INE_CENSO_2024": ["pop_total", "geometry"],
    "SECTRA_EOD": ["h3_origin", "h3_dest", "trips"]
}

def validate_hygienic_invariant(source_name, mapped_keys):
    '''
    Verification: Ensures that all indispensable columns for a given source are mapped.
    Returns: (bool, list_of_missing)
    '''
    indispensable = INDISPENSABLE_COLUMNS.get(source_name, [])
    missing = [col for col in indispensable if col not in mapped_keys]
    return len(missing) == 0, missing

def metadata_audit(source_name, columns):
    '''
    Operational: Maps detected column names from raw files to internal standard keys.
    '''
    mapping = {}
    schema = CHILEAN_SCHEMAS.get(source_name, {})
    for internal, aliases in schema.items():
        # Match if column is exactly the internal name OR in aliases
        all_aliases = [internal] + aliases
        found = [col for col in columns if col in all_aliases]
        if found:
            mapping[internal] = found[0]
    
    if mapping:
        diagnostic_handler.report("METADATA_MAPPING", "INFO", f"Detected {source_name} schema. Mapped {len(mapping)} attributes.")
    return mapping
