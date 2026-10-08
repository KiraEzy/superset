/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership. The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License. You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
/** Version-pinned display-only substitutions in compiled assets; source stays intact. */
module.exports = function (
  this: { resourcePath: string; getOptions: () => { hooks: string } },
  source: string,
) {
  source = source.replaceAll("\r\n", "\n");
  const hooks = this.getOptions().hooks;
  const path = this.resourcePath.replaceAll("\\", "/");
  const replace = (before: string, after: string) => {
    if (source.split(before).length !== 2)
      throw new Error(
        `Localization compatibility check failed: ${path}: ${before}`,
      );
    source = source.replace(before, after);
  };
  if (path.endsWith("/FilterBar/Header/index.tsx")) {
    source = `import { ControlText } from ${JSON.stringify(hooks)};\n` + source;
    replace(
      "{t('Filters and controls')}",
      "<ControlText message=\"filter.heading\" original={t('Filters and controls')} />",
    );
  } else if (path.endsWith("/FilterBar/ActionButtons/index.tsx")) {
    source =
      `import { useControlMessages } from ${JSON.stringify(hooks)};\n` + source;
    replace(
      "const isVertical = filterBarOrientation === FilterBarOrientation.Vertical;",
      "const ui = useControlMessages();\n  const isVertical = filterBarOrientation === FilterBarOrientation.Vertical;",
    );
    replace(
      "{isVertical ? t('Apply filters') : t('Apply')}",
      "{isVertical ? ui('filter.apply', t('Apply filters')) : ui('filter.applyShort', t('Apply'))}",
    );
    replace("{t('Clear all')}", "{ui('filter.clear', t('Clear all'))}");
    replace(
      "title={t(\n              'Some required filters on other tabs have values and will not be cleared',\n            )}",
      "title={ui('filter.otherTabs', t('Some required filters on other tabs have values and will not be cleared'))}",
    );
  } else if (
    path.endsWith("/table/TableChart.tsx") ||
    path.endsWith("/plugin-chart-table/src/TableChart.tsx")
  ) {
    source =
      `import { LocalizedTableSearchInput, LocalizedTablePageSize } from ${JSON.stringify(hooks)};\n` +
      source;
    replace(
      "searchInput={includeSearch && SearchInput}",
      "searchInput={includeSearch && LocalizedTableSearchInput}",
    );
    replace(
      "selectPageSize={pageSize !== null && SelectPageSize}",
      "selectPageSize={pageSize !== null && LocalizedTablePageSize}",
    );
  } else if (path.endsWith("/DataTable/DataTable.tsx")) {
    source = `import { ControlText } from ${JSON.stringify(hooks)};\n` + source;
    replace(
      "{t('Search by')}",
      "<ControlText message=\"table.searchBy\" original={t('Search by')} />",
    );
  } else if (path.endsWith("/Timeseries/EchartsTimeseries.tsx")) {
    source =
      `import { useControlMessages } from ${JSON.stringify(hooks)};\n` + source;
    replace(
      "const { stack } = formData;",
      "const ui = useControlMessages();\n  const { stack } = formData;",
    );
    replace(
      "t('Value: highest first')",
      "ui('chart.desc', t('Value: highest first'))",
    );
    replace(
      "t('Value: lowest first')",
      "ui('chart.asc', t('Value: lowest first'))",
    );
  } else if (
    path.endsWith("/focalbi-rendering/frontend/DashboardBuilder.tsx")
  ) {
    source =
      `import { useControlMessages } from ${JSON.stringify(hooks)};\n` + source;
    replace(
      "const [engine, setEngine] = useState<Engine>(() => {",
      "const ui = useControlMessages();\n  const [engine, setEngine] = useState<Engine>(() => {",
    );
    replace(
      '<label htmlFor="focalbi-renderer">Renderer</label>',
      "<label htmlFor=\"focalbi-renderer\">{ui('renderer.label', 'Renderer')}</label>",
    );
    replace(
      'aria-label="Renderer"',
      "aria-label={ui('renderer.label', 'Renderer')}",
    );
    replace(
      'label: "Superset baseline"',
      "label: ui('renderer.baseline', 'Superset baseline')",
    );
    replace(
      'label: "FocalBI fork"',
      "label: ui('renderer.fork', 'FocalBI fork')",
    );
  } else if (path.endsWith("/DynamicEditableTitle/index.tsx")) {
    source =
      `import { useDisplayTitle } from ${JSON.stringify(hooks)};\n` + source;
    replace(
      "const theme = useTheme();",
      "const theme = useTheme();\n    const displayTitle = useDisplayTitle(title);",
    );
    // Keep native edit state and saves intact; only the readonly value is localized.
    replace(
      "const [currentTitle, setCurrentTitle] = useState(title || '');",
      "const [currentTitle, setCurrentTitle] = useState(title || '');\n    const visibleTitle = isEditing ? currentTitle : displayTitle;",
    );
    replace(
      "sizerRef.current.textContent = currentTitle || placeholder;",
      "sizerRef.current.textContent = visibleTitle || placeholder;",
    );
    replace(
      "}, [currentTitle, placeholder, sizerRef]);",
      "}, [visibleTitle, placeholder, sizerRef]);",
    );
    replace(
      "showTooltip && currentTitle && !isEditing ? currentTitle : null",
      "showTooltip && visibleTitle && !isEditing ? visibleTitle : null",
    );
    replace("value={currentTitle}", "value={visibleTitle}");
  } else if (path.endsWith("/EditableTitle/index.tsx")) {
    source =
      `import { useDisplayTitle } from ${JSON.stringify(hooks)};\n` + source;
    replace(
      "const [isEditing, setIsEditing] = useState(editing);",
      "const displayTitle = useDisplayTitle(title);\n  const [isEditing, setIsEditing] = useState(editing);",
    );
    replace(
      "let value: string | undefined = currentTitle;",
      "let value: string | undefined = isEditing ? currentTitle : displayTitle;",
    );
    replace(
      "measureTextWidth(currentTitle || '', font)",
      "measureTextWidth((isEditing ? currentTitle : displayTitle) || '', font)",
    );
    replace(
      "}, [currentTitle, maxWidth]);",
      "}, [currentTitle, maxWidth, displayTitle, isEditing]);",
    );
  } else if (path.endsWith("/ExploreChartHeader/useExploreMetadataBar.tsx")) {
    source =
      `import { useChartDescription } from ${JSON.stringify(hooks)};\n` +
      source;
    replace(
      ") =>\n  useMemo(() => {",
      ") => {\n  const localizedDescription = useChartDescription(slice?.slice_id, slice?.description || '');\n  return useMemo(() => {",
    );
    replace("if (slice?.description) {", "if (localizedDescription.text) {");
    replace("value: slice?.description,", "value: localizedDescription.text,");
    replace(
      "}, [metadata, slice?.description]);",
      "}, [metadata, localizedDescription.text]);\n};",
    );
  } else if (path.endsWith("/gridComponents/Chart/Chart.tsx")) {
    source =
      `import { useChartDescription } from ${JSON.stringify(hooks)};\n` +
      source;
    replace(
      "const sliceSliceId = slice.slice_id;",
      "const sliceSliceId = slice.slice_id;\n  const localizedDescription = useChartDescription(sliceSliceId, slice.description || '');",
    );
    replace(
      "}, [isExpanded]);",
      "}, [isExpanded, localizedDescription.text]);",
    );
    replace(
      "{isExpanded && slice.description_markdown && (",
      "{isExpanded && (localizedDescription.text || slice.description_markdown) && (",
    );
    replace(
      "dangerouslySetInnerHTML={{\n            __html: slice.description_markdown,\n          }}",
      "{...(localizedDescription.translated ? { children: localizedDescription.node } : { dangerouslySetInnerHTML: { __html: slice.description_markdown } })}",
    );
    replace(
      "aria-label={slice.description}",
      "aria-label={localizedDescription.text}",
    );
  } else if (path.endsWith("/FilterControls/FilterControl.tsx")) {
    source =
      `import { useFilterText } from ${JSON.stringify(hooks)};\n` + source;
    replace(
      "const { name = '<undefined>' } = filter;",
      "const name = useFilterText(filter.id, 'name', filter.name || '<undefined>');\n  const localizedDescription = useFilterText(filter.id, 'description', filter.description || '');",
    );
    replace("filter.description?.trim()", "localizedDescription.trim()");
    replace(
      "description={filter.description}",
      "description={localizedDescription}",
    );
    replace("      filter.description,", "      localizedDescription,");
  } else if (path.endsWith("/Select/SelectFilterPlugin.tsx")) {
    source =
      `import { useFilterDisplay, useControlMessages, FilterDropdown, filterDropdownBlur, filterDropdownKeyDown } from ${JSON.stringify(hooks)};\n` +
      source;
    replace(
      "export default function PluginFilterSelect(props: PluginFilterSelectProps) {",
      "export default function PluginFilterSelect(props: PluginFilterSelectProps) {\n  const localization = useFilterDisplay();\n  const ui = useControlMessages();",
    );
    replace(
      "      label: labelFormatter(value, datatype),",
      "      label: localization.label(value, String(labelFormatter(value, datatype))),\n      nativeLabel: labelFormatter(value, datatype),",
    );
    replace(
      "}, [data, datatype, col, labelFormatter]);",
      "}, [data, datatype, col, labelFormatter, localization.revision]);",
    );
    replace(
      "        label: search,",
      "        label: search,\n        nativeLabel: search,",
    );
    replace(
      "const labelComparator = propertyComparator('label');",
      "const labelComparator = propertyComparator('nativeLabel');",
    );
    replace("t('No data')", "ui('filter.noData', t('No data'))");
    replace(
      "tn('%s option', '%s options', data.length, data.length)",
      "ui(data.length === 1 ? 'filter.option' : 'filter.options', tn('%s option', '%s options', data.length, data.length), { count: data.length })",
    );
    replace("t('is not')", "ui('filter.isNot', t('is not'))");
    replace("t('is')", "ui('filter.is', t('is'))");
      replace("            allowClear", "            allowClear={!multiSelect}");
    replace(
      "            allowSelectAll={!searchAllOptions}",
      `            allowSelectAll={false}
            {...(multiSelect ? {
              onKeyDownCapture: filterDropdownKeyDown,
              onBlurCapture: filterDropdownBlur,
              popupRender: (menu: React.ReactElement) => (
                <FilterDropdown options={options} value={filterState.value}
                  disabled={isDisabled || isRefreshing}
                  onChange={values => handleChange(values as SelectValue)}>
                  {menu}
                </FilterDropdown>
              ),
            } : {})}`,
    );
  }
  return source;
};
