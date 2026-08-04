"""PDF processing constants.

PAGE_SEPARATOR joins page texts for global offsets. It never maps to PDF coordinates;
entities that land only on separator characters raise ENTITY_MAPPING_FAILED.
"""

PAGE_SEPARATOR = "\n\f"
