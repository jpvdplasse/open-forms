import {useFormikContext} from 'formik';
import {FormattedMessage} from 'react-intl';

import Field from 'components/admin/forms/Field';
import FormRow from 'components/admin/forms/FormRow';
import {TextInput} from 'components/admin/forms/Inputs';
import {TargetPathSelect} from 'components/admin/forms/objects_api';
import ErrorMessage from 'components/errors/ErrorMessage';

import {ShowJSONSchemaToggle} from './edit_options/generic';
import {useFetchTargetPaths, useVariableJsonSchema} from './edit_options/hooks';

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
  const {getFieldProps} = useFormikContext();

  const variableSchema = useVariableJsonSchema(variable, components);
  const {loading, targetPaths, error} = useFetchTargetPaths({
    objectsApiGroup,
    objecttype,
    objecttypeVersion,
    variableJsonSchema: variableSchema,
  });

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
          required
          noManageChildProps
        >
          <TargetPathSelect
            name={`${namePrefix}.targetPath`}
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
