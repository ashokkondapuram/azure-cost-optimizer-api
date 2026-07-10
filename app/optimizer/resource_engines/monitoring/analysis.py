"""Compatibility aggregate — functions moved to it_services."""
from it_services.monitoring_loganalytics.engine.analysis import analyze_log_analytics
from it_services.monitoring_appinsights.engine.analysis import analyze_app_insights

__all__ = ['analyze_log_analytics', 'analyze_app_insights']
