import PropTypes from 'prop-types';
import {useContext} from 'react';
import {FormattedMessage} from 'react-intl';

import ModalOptionsConfiguration from 'components/admin/forms/ModalOptionsConfiguration';
import {ValidationErrorContext, filterErrors} from 'components/admin/forms/ValidationErrors';

import VeridOptionsFormFields from './VeridOptionsFormFields';

const VeridOptionsForm = ({name, label, plugin, authBackend, onChange}) => {
  const validationErrors = useContext(ValidationErrorContext);
  const numErrors = filterErrors(name, validationErrors).length;

  return (
    <ModalOptionsConfiguration
      name={name}
      label={label}
      numErrors={numErrors}
      modalTitle={
        <FormattedMessage
          description="Ver.iD authentication options modal title"
          defaultMessage="Plugin configuration: Ver.iD wallet"
        />
      }
      initialFormData={{clientId: '', clientSecret: '', ...authBackend.options}}
      onSubmit={values => onChange({formData: values})}
    >
      <VeridOptionsFormFields name={name} plugin={plugin} />
    </ModalOptionsConfiguration>
  );
};

VeridOptionsForm.propTypes = {
  name: PropTypes.string.isRequired,
  label: PropTypes.node.isRequired,
  authBackend: PropTypes.shape({
    backend: PropTypes.string.isRequired,
    options: PropTypes.shape({
      client_id: PropTypes.string,
      client_secret: PropTypes.string,
    }),
  }).isRequired,
  plugin: PropTypes.object,
  onChange: PropTypes.func.isRequired,
};

export default VeridOptionsForm;
