import {useAsync} from 'react-use';

import {getCatalogueOption, groupAndSortCatalogueOptions} from 'components/admin/forms/zgw';
import {get} from 'utils/fetch';

const CATALOGUES_ENDPOINT = '/api/v2/objects-api/catalogues';

/**
 * @param  {number} apiGroupID
 */
const getCatalogues = async apiGroupID => {
  const response = await get(CATALOGUES_ENDPOINT, {objects_api_group: apiGroupID});
  if (!response.ok) {
    throw new Error('Loading available catalogues failed');
  }
  return groupAndSortCatalogueOptions(response.data);
};

/**
 * Look up the available catalogues and selected catalogue URL for a given API Group.
 *
 * @typedef {{
 *   domain: string;
 *   rsin: string;
 * }} Catalogue
 *
 * @param {number|null} objectsApiGroup
 * @param {Catalogue|undefined} catalogue
 */
export const useResolveCatalogue = (objectsApiGroup, catalogue) => {
  // fetch available catalogues and re-use the result
  const {
    loading,
    value: catalogueOptionGroups = [],
    error,
  } = useAsync(async () => {
    if (!objectsApiGroup) return [];
    return await getCatalogues(objectsApiGroup);
  }, [objectsApiGroup]);

  const catalogueValue = getCatalogueOption(catalogueOptionGroups, catalogue || {});
  const catalogueUrl = catalogueValue?.url;
  return {
    loading,
    catalogueOptionGroups,
    error,
    catalogueUrl,
  };
};
