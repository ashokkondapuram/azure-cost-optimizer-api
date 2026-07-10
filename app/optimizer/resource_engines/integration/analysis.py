"""Compatibility aggregate — functions moved to it_services."""
from it_services.integration_apim.engine.analysis import analyze_apim
from it_services.integration_datafactory.engine.analysis import analyze_data_factories
from it_services.integration_logicapp.engine.analysis import analyze_logic_apps

__all__ = ['analyze_apim', 'analyze_data_factories', 'analyze_logic_apps']
