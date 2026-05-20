import {useFormikContext} from 'formik';
import {FormattedMessage} from 'react-intl';

import Field from 'components/admin/forms/Field';
import FormRow from 'components/admin/forms/FormRow';
import {Checkbox} from 'components/admin/forms/Inputs';
import ErrorMessage from 'components/errors/ErrorMessage';

import {MappedVariableTargetPathSelect} from './GenericObjectsApiVariableConfigurationEditor';
import {ShowJSONSchemaToggle} from './edit_options/generic';
import {useFetchTargetPaths, useVariableJsonSchema} from './edit_options/hooks';

export const MapEditor = ({
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
  const {setFieldValue} = useFormikContext();
  const {geometryVariableKey} = backendOptions;

  const isGeometry = geometryVariableKey && geometryVariableKey === variable.key;

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
        <Field name="geometryVariableKey" disabled={!!mappedVariable.targetPath}>
          <Checkbox
            name="geometryCheckbox"
            label={
              <FormattedMessage
                defaultMessage="Map to geometry field"
                description="'Map to geometry field' checkbox label"
              />
            }
            helpText={
              <FormattedMessage
                description="'Map to geometry field' checkbox help text"
                defaultMessage="Whether to map this variable to the {geometryPath} attribute"
                values={{geometryPath: <code>record.geometry</code>}}
              />
            }
            checked={isGeometry}
            onChange={event => {
              const newValue = event.target.checked ? variable.key : undefined;
              setFieldValue('geometryVariableKey', newValue);
            }}
          />
        </Field>
      </FormRow>
      <FormRow>
        <Field
          name={`${namePrefix}.targetPath`}
          label={
            <FormattedMessage
              defaultMessage="JSON Schema target"
              description="'JSON Schema target' label"
            />
          }
          disabled={isGeometry}
        >
          <MappedVariableTargetPathSelect
            name={`${namePrefix}.targetPath`}
            index={index}
            mappedVariable={mappedVariable}
            isDisabled={isGeometry}
            isLoading={loading}
            targetPaths={targetPaths}
          />
        </Field>
      </FormRow>

      <ShowJSONSchemaToggle availablePaths={targetPaths} targetPath={mappedVariable.targetPath} />
    </>
  );
};
