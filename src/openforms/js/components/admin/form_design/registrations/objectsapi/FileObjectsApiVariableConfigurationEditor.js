import {useFormikContext} from 'formik';
import {useContext} from 'react';
import {FormattedMessage} from 'react-intl';
import {useAsync} from 'react-use';

import {APIContext} from 'components/admin/form_design/Context';
import Field from 'components/admin/forms/Field';
import FormRow from 'components/admin/forms/FormRow';
import {TextInput} from 'components/admin/forms/Inputs';
import ErrorMessage from 'components/errors/ErrorMessage';

import {MappedVariableTargetPathSelect} from './GenericObjectsApiVariableConfigurationEditor';
import {ShowJSONSchemaToggle} from './edit_options/generic';
import {asJsonSchema} from './utils';
import {fetchTargetPaths} from './utils';

/**
 * Registration options UI/editor for file components.
 */
export const FileEditor = ({
  variable,
  components,
  namePrefix,
  index,
  mappedVariable,
  objecttype,
  objectsApiGroup,
  objecttypeVersion,
  backendOptions,
}) => {
  const {csrftoken} = useContext(APIContext);
  const {getFieldProps} = useFormikContext();

  const {
    loading,
    value: targetPaths,
    error,
  } = useAsync(async () => {
    const results = fetchTargetPaths(
      csrftoken,
      objectsApiGroup,
      objecttype,
      objecttypeVersion,
      asJsonSchema(variable, components)
    );

    return results;
  }, []);

  if (error)
    return (
      <ErrorMessage>
        <FormattedMessage
          description="Objects API variable registration configuration API error"
          defaultMessage="Something went wrong when fetching the available target paths"
        />
      </ErrorMessage>
    );

  return (
    <>
      <FormRow>
        <Field
          name={`${namePrefix}.targetPath`}
          label={
            <FormattedMessage
              defaultMessage="JSON Schema target"
              description="'JSON Schema target' label"
            />
          }
        >
          <MappedVariableTargetPathSelect
            name={`${namePrefix}.targetPath`}
            index={index}
            mappedVariable={mappedVariable}
            isLoading={loading}
            targetPaths={targetPaths}
          />
        </Field>
      </FormRow>
      <FormRow>
        <Field
          {...getFieldProps(`${namePrefix}.options.organizationRsin`)}
          label={
            <FormattedMessage
              description="Document upload: organizationRsin option label"
              defaultMessage="Organization RSIN"
            />
          }
          helpText={
            <FormattedMessage
              description="Document upload: organizationRsin option help text"
              defaultMessage={`RSIN of the organization that registers the document in
              the Documents API. If left blank, the general configuration is used.`}
            />
          }
        >
          <TextInput name={`${namePrefix}.organizationRsin`} maxLength="9" />
        </Field>
      </FormRow>

      <ShowJSONSchemaToggle availablePaths={targetPaths} targetPath={mappedVariable.targetPath} />
    </>
  );
};
