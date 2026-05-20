import {useFormikContext} from 'formik';
import {useContext} from 'react';
import {FormattedMessage} from 'react-intl';
import {useAsync} from 'react-use';

import {APIContext} from 'components/admin/form_design/Context';
import Field from 'components/admin/forms/Field';
import FormRow from 'components/admin/forms/FormRow';
import {Checkbox} from 'components/admin/forms/Inputs';
import ErrorMessage from 'components/errors/ErrorMessage';

import {MappedVariableTargetPathSelect} from './GenericObjectsApiVariableConfigurationEditor';
import {asJsonSchema} from './utils';
import {fetchTargetPaths} from './utils';

export const SelectboxesEditor = ({
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
  const {setFieldValue} = useFormikContext();
  const {transformToList = []} = backendOptions;

  const transformationNeeded = transformToList.includes(variable.key);

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
      asJsonSchema(variable, components, transformToList)
    );

    return results;
  }, [transformationNeeded]);

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
        <Field name="transformToList">
          <Checkbox
            name="transformToListCheckbox"
            label={
              <FormattedMessage
                defaultMessage="Transform to list"
                description="'Transform to list' checkbox label"
              />
            }
            helpText={
              <FormattedMessage
                description="'Transform to list' checkbox help text"
                defaultMessage="If enabled, the selected values are sent as an array of values instead of an object with a boolean value for each option."
              />
            }
            checked={transformToList.includes(variable.key) || false}
            onChange={event => {
              const shouldBeTransformed = event.target.checked;
              const newTransformToList = shouldBeTransformed
                ? [...transformToList, variable.key]
                : transformToList.filter(key => key !== variable.key);
              setFieldValue('transformToList', newTransformToList);
              setFieldValue(`${namePrefix}.targetPath`, undefined);
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
