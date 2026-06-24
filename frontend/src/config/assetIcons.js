/**
 * Logical icon keys for pages, routes, and API paths.
 * Icons render via react-az-icons (open source).
 */
import {
  iconKeyFromResourceId,
  iconKeyForAzureType,
  iconKeyForApiPath,
} from './azureIconRegistry';

export {
  PAGE_ICON_KEYS as PAGE_ICONS,
  NAV_GROUP_KEYS as NAV_GROUP_ICONS,
  CATEGORY_KEYS as CATEGORY_ICONS,
  ARM_TYPE_KEYS as AZURE_TYPE_ICONS,
  ROUTE_ICON_KEYS as ROUTE_ICONS,
  API_PATH_KEYS as API_PATH_ICONS,
  iconKeyForAzureType as iconForAzureType,
  iconKeyForCategory as iconForCategory,
  iconKeyForComponent as iconForComponent,
  iconKeyForRoute as iconForRoute,
  iconKeyForApiPath as iconForApiPath,
  iconKeyFromResourceId as iconFromResourceId,
} from './azureIconRegistry';

export function iconForRow(row, { apiPath, fallback } = {}) {
  return (
    iconKeyFromResourceId(row?.resource_id || row?.id)
    || iconKeyForAzureType(row?.type)
    || iconKeyForApiPath(apiPath)
    || fallback
    || 'default'
  );
}
