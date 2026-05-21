import {useField, useFormikContext} from 'formik';
import {FormattedMessage} from 'react-intl';

import Field from 'components/admin/forms/Field';
import FormRow from 'components/admin/forms/FormRow';
import {TextInput} from 'components/admin/forms/Inputs';
import ReactSelect from 'components/admin/forms/ReactSelect';
import {TargetPathSelect} from 'components/admin/forms/objects_api';
import ErrorMessage from 'components/errors/ErrorMessage';

import {ShowJSONSchemaToggle} from './generic';
import {useFetchTargetPaths, useVariableJsonSchema} from './hooks';

/**
 * Registration options UI/editor for file components.
 */
const FileEditor = ({
  variable,
  components,
  namePrefix,
  mappedVariable,
  objecttype,
  objectsApiGroup,
  objecttypeVersion,
  backendOptions,
}) => {
  const {catalogue} = backendOptions;

  const variableSchema = useVariableJsonSchema(variable, components);
  const {loading, targetPaths, error} = useFetchTargetPaths({
    objectsApiGroup,
    objecttype,
    objecttypeVersion,
    variableJsonSchema: variableSchema,
  });

  if (catalogue) {
    console.log(catalogue);
  }

  if (error) {
    return (
      <ErrorMessage>
        <FormattedMessage
          description="Objects API variable registration configuration API error"
          defaultMessage="Something went wrong when fetching the available target paths"
        />
      </ErrorMessage>
    );
  }

  return (
    <>
      <TargetPath namePrefix={namePrefix} loading={loading} targetPaths={targetPaths} />
      <OrganizationRSIN namePrefix={namePrefix} />
      <ConfidentialityLevel namePrefix={namePrefix} />
      <Title namePrefix={namePrefix} />
      <ShowJSONSchemaToggle availablePaths={targetPaths} targetPath={mappedVariable.targetPath} />
    </>
  );
};

const TargetPath = ({namePrefix, loading, targetPaths}) => (
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
);

const OrganizationRSIN = ({namePrefix}) => {
  const [props] = useField(`${namePrefix}.options.organizationRsin`);
  return (
    <FormRow>
      <Field
        name={props.name}
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
        <TextInput {...props} maxLength="9" />
      </Field>
    </FormRow>
  );
};

const CONFIDENTIALITY_OPTIONS = [
  {value: 'openbaar', label: 'Openbaar'},
  {value: 'beperkt_openbaar', label: 'Beperkt openbaar'},
  {value: 'intern', label: 'Intern'},
  {value: 'zaakvertrouwelijk', label: 'Zaakvertrouwelijk'},
  {value: 'vertrouwelijk', label: 'Vertrouwelijk'},
  {value: 'confidentieel', label: 'Confidentieel'},
  {value: 'geheim', label: 'Geheim'},
  {value: 'zeer_geheim', label: 'Zeer geheim'},
];

const ConfidentialityLevel = ({namePrefix}) => (
  <FormRow>
    <Field
      name={`${namePrefix}.options.confidentialityLevel`}
      label={
        <FormattedMessage
          description="Document upload: confidentialityLevel label"
          defaultMessage="Confidentiality"
        />
      }
      helpText={
        <FormattedMessage
          description="Document upload: confidentialityLevel option help text"
          defaultMessage={`Indication of the level to which extent the document is meant
          to be public. Only provide this if you wish to override the default from the
          configured document type.`}
        />
      }
      noManageChildProps
    >
      <ReactSelect
        name={`${namePrefix}.options.confidentialityLevel`}
        options={CONFIDENTIALITY_OPTIONS}
        isClearable
      />
    </Field>
  </FormRow>
);

const Title = ({namePrefix}) => {
  const [props] = useField(`${namePrefix}.options.title`);
  return (
    <FormRow>
      <Field
        name={props.name}
        label={
          <FormattedMessage
            description="Document upload: title option label"
            defaultMessage="Title"
          />
        }
        helpText={
          <FormattedMessage
            description="Document upload: title option help text"
            defaultMessage={`Optional custom title for the document. By default, the
            form name is used.`}
          />
        }
      >
        <TextInput {...props} maxLength="200" />
      </Field>
    </FormRow>
  );
};

export default FileEditor;
