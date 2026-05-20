import {FieldArray, useFormikContext} from 'formik';
import PropTypes from 'prop-types';
import {useContext} from 'react';
import {FormattedMessage} from 'react-intl';
import {useAsync} from 'react-use';

import {APIContext} from 'components/admin/form_design/Context';
import Field from 'components/admin/forms/Field';
import FormRow from 'components/admin/forms/FormRow';
import {TargetPathSelect} from 'components/admin/forms/objects_api';
import ErrorMessage from 'components/errors/ErrorMessage';

import {ShowJSONSchemaToggle} from './edit_options/generic';
import {asJsonSchema} from './utils';
import {fetchTargetPaths} from './utils';

/**
 * Hack-ish way to manage the variablesMapping state for one particular entry.
 *
 * We ensure that an item is added to `variablesMapping` by using the `FieldArray`
 * helper component if it doesn't exist yet, otherwise we update it.
 */
export const MappedVariableTargetPathSelect = ({
  name,
  index,
  mappedVariable,
  isLoading = false,
  targetPaths = [],
  isDisabled = false,
}) => {
  const {
    values: {variablesMapping = []},
    setFieldValue,
  } = useFormikContext();
  const isNew = variablesMapping.length === index;
  return (
    <FieldArray
      name="variablesMapping"
      render={arrayHelpers => (
        <TargetPathSelect
          name={name}
          isLoading={isLoading}
          targetPaths={targetPaths}
          isDisabled={isDisabled}
          onChange={newValue => {
            // Clearing the select means we need to remove the record from the mapping,
            // otherwise it's not a valid item for the backend.
            if (newValue === null) {
              arrayHelpers.remove(index);
              return;
            }

            // otherwise, either add a new item, or update the existing
            if (isNew) {
              const newMapping = {...mappedVariable, targetPath: newValue.targetPath};
              arrayHelpers.push(newMapping);
            } else {
              setFieldValue(name, newValue.targetPath);
            }
          }}
        />
      )}
    />
  );
};

MappedVariableTargetPathSelect.propTypes = {
  name: PropTypes.string.isRequired,
  index: PropTypes.number.isRequired,
  mappedVariable: PropTypes.shape({
    variableKey: PropTypes.string.isRequired,
    targetPath: PropTypes.arrayOf(PropTypes.string),
    options: PropTypes.object,
  }).isRequired,
  isLoading: PropTypes.bool,
  isDisabled: PropTypes.bool,
};

export const GenericEditor = ({
  variable,
  components,
  namePrefix,
  index,
  mappedVariable,
  objecttype,
  objectsApiGroup,
  objecttypeVersion,
}) => {
  const {csrftoken} = useContext(APIContext);

  // Load all the possible target paths in parallel depending on if the data should be
  // transformed or not
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

      <ShowJSONSchemaToggle availablePaths={targetPaths} targetPath={mappedVariable.targetPath} />
    </>
  );
};
