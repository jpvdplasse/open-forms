import {FormattedMessage} from 'react-intl';

import Field from 'components/admin/forms/Field';
import FormRow from 'components/admin/forms/FormRow';
import {TargetPathSelect} from 'components/admin/forms/objects_api';
import ErrorMessage from 'components/errors/ErrorMessage';

import {ShowJSONSchemaToggle} from '.';
import {useFetchTargetPaths, useVariableJsonSchema} from '../hooks';

const GenericEditor = ({
  variable,
  components,
  namePrefix,
  mappedVariable,
  objecttype,
  objectsApiGroup,
  objecttypeVersion,
}) => {
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

      <ShowJSONSchemaToggle availablePaths={targetPaths} targetPath={mappedVariable.targetPath} />
    </>
  );
};

export default GenericEditor;
