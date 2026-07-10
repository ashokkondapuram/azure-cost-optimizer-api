"""Compatibility aggregate — functions moved to it_services."""
from it_services.analytics_databricks.engine.analysis import analyze_databricks
from it_services.analytics_synapse.engine.analysis import analyze_synapse
from it_services.analytics_adx.engine.analysis import analyze_adx
from it_services.analytics_mlworkspace.engine.analysis import analyze_ml_workspaces

__all__ = ['analyze_databricks', 'analyze_synapse', 'analyze_adx', 'analyze_ml_workspaces']
