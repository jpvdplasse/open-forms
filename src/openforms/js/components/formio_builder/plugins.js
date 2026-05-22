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

  // Ver.iD claim names are scoped to the disclosure flow selected on the
  // form's auth backend. If we know the flow, query its claims; otherwise
  // fall back to an empty list.
  if (plugin === 'verid') {
    const {authBackends = []} = context;
    const veridBackend = authBackends.find(b => b.backend === 'verid_oidc');
    // Tolerate both camelCase (JSON wire format) and snake_case (raw model
    // dict) — should be camelCase in practice but defensive doesn't hurt.
    const opts = veridBackend?.options || {};
    const clientId = opts.clientId || opts.client_id || '';
    if (!clientId) return [];
    const resp = await get(
      `/api/v2/authentication/plugins/verid/disclosures/${encodeURIComponent(clientId)}/claims`
    );
    if (!resp.ok) return [];
    return (resp.data || []).map(c => ({id: c.claim, label: c.name || c.claim}));
  }

  const resp = await get(`/api/v2/prefill/plugins/${plugin}/attributes`);
  return resp.data;
};
