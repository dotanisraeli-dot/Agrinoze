import sys, os
# Add parent dir so '01_engine' (renamed via symlink) is importable as 'agrinoze'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Create agrinoze alias if not already present
import importlib, types
if 'agrinoze' not in sys.modules:
    # Point 'agrinoze' at the 01_engine package
    engine_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(engine_dir))
    # Import the package by its folder name and alias it
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "agrinoze", os.path.join(engine_dir, "__init__.py"),
        submodule_search_locations=[engine_dir],
    )
    agrinoze = importlib.util.module_from_spec(spec)
    sys.modules['agrinoze'] = agrinoze
    spec.loader.exec_module(agrinoze)
