import {useField} from 'formik';
import PropTypes from 'prop-types';
import {useEffect, useState} from 'react';
import {FormattedMessage} from 'react-intl';

import Field from 'components/admin/forms/Field';
import Fieldset from 'components/admin/forms/Fieldset';
import FormRow from 'components/admin/forms/FormRow';
import {TextInput} from 'components/admin/forms/Inputs';
import ReactSelect from 'components/admin/forms/ReactSelect';

import {get} from 'utils/fetch';

const DISCLOSURES_URL = '/api/v2/authentication/plugins/verid/disclosures';

const DisclosureField = () => {
  const [field, , helpers] = useField('clientId');
  const [options, setOptions] = useState([]);
  const [available, setAvailable] = useState(true);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    get(DISCLOSURES_URL)
      .then(response => {
        if (cancelled) return;
        // 503 → GraphQL not configured; fall back to text input
        if (response.statusCode === 503) {
          setAvailable(false);
          return;
        }
        const opts = (response.data || []).map(d => ({
          value: d.uuid,
          label: `${d.name} (${d.uuid.slice(0, 8)}…)`,
        }));
        // Always make sure the currently-stored value is in the options list,
        // even if it didn't come back from the API (e.g. flow was deactivated).
        // Otherwise react-select would render an empty box for a saved value.
        if (field.value && !opts.find(o => o.value === field.value)) {
          opts.unshift({value: field.value, label: field.value});
        }
        setOptions(opts);
      })
      .catch(() => !cancelled && setAvailable(false))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // Re-fetch when the saved value changes (e.g. modal re-opened on a
    // different form). We deliberately depend on field.value here.
  }, [field.value]);

  const label = (
    <FormattedMessage
      description="Ver.iD disclosure flow field label"
      defaultMessage="Disclosure flow"
    />
  );
  const helpText = (
    <FormattedMessage
      description="Ver.iD disclosure flow help text"
      defaultMessage="The Ver.iD Studio disclosure flow whose UUID becomes the OAuth client_id for this form."
    />
  );

  // If GraphQL isn't available, show a plain text input.
  if (!available) {
    return (
      <FormRow>
        <Field name="clientId" label={label} helpText={helpText} required>
          <TextInput
            name="clientId"
            value={field.value || ''}
            onChange={e => helpers.setValue(e.target.value)}
            placeholder="e.g. 8435f0d9-8d90-402c-bdb8-ebac8450583a"
          />
        </Field>
      </FormRow>
    );
  }

  // SelectWithFormik reads the value from Formik via `useField` internally,
  // so we don't pass value/onChange explicitly — that would override the
  // built-in option lookup and leave the saved value invisible on re-open.
  return (
    <FormRow>
      <Field name="clientId" label={label} helpText={helpText} required>
        <ReactSelect name="clientId" options={options} isLoading={loading} />
      </Field>
    </FormRow>
  );
};

const ClientSecretField = () => {
  const [field, , helpers] = useField('clientSecret');
  return (
    <FormRow>
      <Field
        name="clientSecret"
        label={
          <FormattedMessage
            description="Ver.iD client secret field label"
            defaultMessage="Client secret (optional)"
          />
        }
        helpText={
          <FormattedMessage
            description="Ver.iD client secret help text"
            defaultMessage="Leave blank for public/PKCE disclosure flows (the default). Only fill in if Ver.iD Studio explicitly configured a client secret for this flow."
          />
        }
      >
        <TextInput
          name="clientSecret"
          value={field.value || ''}
          onChange={e => helpers.setValue(e.target.value)}
        />
      </Field>
    </FormRow>
  );
};

const VeridOptionsFormFields = () => (
  <Fieldset>
    <DisclosureField />
    <ClientSecretField />
  </Fieldset>
);

VeridOptionsFormFields.propTypes = {
  name: PropTypes.string.isRequired,
  plugin: PropTypes.object,
};

export default VeridOptionsFormFields;
