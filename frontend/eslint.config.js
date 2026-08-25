import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
  },
  {
    rules: {
      'vue/multi-word-component-names': 'off',
      'vue/no-v-html': 'off',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
  {
    // src/api/generated.ts is produced from the backend's OpenAPI schema and is
    // regenerated over any hand edit, so a finding in it cannot be actioned where
    // it is reported. The single ERROR in this project is an empty request-body
    // interface there, which generated code cannot avoid.
    //
    // This silences THAT RULE for THAT FILE rather than ignoring the file. Ignoring
    // it would switch off every other check on 500+ lines of API surface and hide a
    // genuinely broken generation; this leaves them all running.
    files: ['src/api/generated.ts'],
    rules: { '@typescript-eslint/no-empty-object-type': 'off' },
  },
]
