import {getPrefillAttributes as getYiviPrefillAttributes} from 'components/admin/form_design/variables/prefill/yivi/YiviFields';
import {getYiviAttributeGroups} from 'components/admin/forms/yivi/AttributeGroups';
import {get} from 'utils/fetch';

export const getValidatorPlugins = async componentType => {
  const resp = await get(
    '/api/v2/validation/plugins',
    componentType ? {componentType: componentType} : {}
  );
  return resp.data;
};

export const getRegistrationAttributes = async () => {
  const resp = await get('/api/v2/registration/attributes');
  return resp.data;
};

export const getPrefillPlugins = async componentType => {
  const resp = await get('/api/v2/prefill/plugins', {componentType});
  return resp.data;
};

export const getPrefillAttributes = async (plugin, context = {}) => {
  // special case yivi which takes the surrounding form context into account
  if (plugin === 'yivi') {
    const attributeGroups = await getYiviAttributeGroups();
    const {availablePrefillPlugins, authBackends} = context;
    const attributes = getYiviPrefillAttributes(
      availablePrefillPlugins,
      authBackends,
      attributeGroups
    );
    return attributes.map(([attribute, label]) => ({id: attribute, label}));
  }

  // If the plugin declares a custom attributes endpoint, use it instead of the
  // default static list. This lets third-party plugins supply context-aware
  // attributes without requiring changes to this file.
  const {availablePrefillPlugins = []} = context;
  const pluginMeta = availablePrefillPlugins.find(p => p.id === plugin);
  if (pluginMeta?.customAttributesUrl) {
    const resp = await get(pluginMeta.customAttributesUrl);
    if (!resp.ok) return [];
    return (resp.data || []).map(item => ({id: item.id, label: item.label || item.id}));
  }

  const resp = await get(`/api/v2/prefill/plugins/${plugin}/attributes`);
  return resp.data;
};
