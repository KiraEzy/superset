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
import { Bundle, category, label, Resource, Scalar, Locale } from "./contracts";
import { controlMessage, localizeTotal } from "./controls";
type ObjectValue = Record<string, unknown>;
const object = (value: unknown): ObjectValue =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as ObjectValue)
    : {};
const array = (value: unknown): unknown[] =>
  Array.isArray(value) ? value : value ? [value] : [];
function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (value) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        value
      ]!,
  );
}
export interface Presentation {
  locale?: Locale;
  nativeTotalTemplate?: string;
  chart?: Resource;
  dataset?: Resource;
  instance?: Resource;
  dimensions: string[];
  sourceControls?: ObjectValue;
}
export function presentation(
  bundle: Bundle | undefined,
  chartId: string,
  instanceKey?: string,
  dimensions: string[] = [],
): Presentation {
  const binding = bundle?.charts[chartId];
  const dashboard = bundle?.resources[`dashboard/${bundle.uuid}`];
  const instance =
    dashboard && instanceKey
      ? {
          ...dashboard,
          fields: dashboard.fields
            .filter((field) =>
              field.key.startsWith(`layout/${instanceKey}/chart/`),
            )
            .map((field) => ({
              ...field,
              key: field.key.slice(`layout/${instanceKey}/chart/`.length),
            })),
          translations: Object.fromEntries(
            Object.entries(dashboard.translations)
              .filter(([key]) => key.startsWith(`layout/${instanceKey}/chart/`))
              .map(([key, value]) => [
                key.slice(`layout/${instanceKey}/chart/`.length),
                value,
              ]),
          ),
        }
      : undefined;
  return {
    chart: binding && bundle?.resources[`chart/${binding.uuid}`],
    dataset: binding?.datasetUuid
      ? bundle?.resources[`dataset/${binding.datasetUuid}`]
      : undefined,
    instance,
    dimensions,
  };
}
export function displayLabel(context: Presentation, raw: string): string {
  return label(
    context.instance,
    raw,
    label(context.chart, raw, label(context.dataset, raw, raw)),
  );
}
export function displayCategory(
  context: Presentation,
  raw: Scalar,
  column?: string,
): string {
  const targets = column ? [column] : context.dimensions;
  for (const target of targets) {
    const translated = category(context.dataset, target, raw);
    if (translated !== undefined) return translated;
  }
  return String(raw ?? "");
}
/** Decorate only display formatters/headers. All series, row and column keys survive. */
export function localizeProps(
  type: string,
  raw: ObjectValue,
  context: Presentation,
): ObjectValue {
  const adapters: Record<
    string,
    (value: ObjectValue, context: Presentation) => ObjectValue
  > = {
    big_number_total: localizeKpi,
    pie: localizeEcharts,
    echarts_timeseries_bar: localizeEcharts,
    mixed_timeseries: localizeEcharts,
    table: localizeTable,
    filter_select: localizeSelect,
  };
  return adapters[type]?.(raw, context) || raw;
}
function localizeKpi(raw: ObjectValue, context: Presentation): ObjectValue {
  const result = localizeEcharts(raw, context);
  for (const key of ["header", "subheader", "subtitle"]) {
    if (typeof result[key] === "string")
      result[key] = control(context, key, result[key] as string);
  }
  return result;
}
function control(
  context: Presentation,
  name: string,
  original: string,
): string {
  for (const resource of [context.instance, context.chart]) {
    const field = resource?.fields.find(
      (item) => item.key === `control/${name}`,
    );
    const current = context.sourceControls
      ? String(context.sourceControls[name] ?? "")
      : field?.source;
    if (
      field &&
      field.source === current &&
      resource?.translations[field.key]?.text
    )
      return resource.translations[field.key].text!;
  }
  return original;
}
function localizeEcharts(raw: ObjectValue, context: Presentation): ObjectValue {
  if (!raw.echartOptions) return raw;
  const options = object(raw.echartOptions);
  const series = array(options.series).map((item) => {
    const serie = object(item);
    const labels = object(serie.label);
    const previous = labels.formatter;
    return {
      ...serie,
      label: {
        ...labels,
        formatter: (params: ObjectValue) => {
          const name = String(params.name ?? "");
          const translated = displayCategory(context, name);
          if (typeof previous === "function")
            return String(previous(params)).split(name).join(translated);
          if (typeof previous === "string")
            return previous
              .replaceAll("{b}", translated)
              .replaceAll("{c}", String(params.value ?? ""))
              .replaceAll("{d}", String(params.percent ?? ""));
          return translated;
        },
      },
    };
  });
  const axis = (value: unknown, name: string) =>
    array(value).map((item, index) => {
      const current = object(item);
      const previous = object(current.axisLabel).formatter;
      return {
        ...current,
        name: control(
          context,
          index === 1 && name === "y_axis_title"
            ? "y_axis_title_secondary"
            : name,
          String(current.name ?? ""),
        ),
        axisLabel: {
          ...object(current.axisLabel),
          formatter: (value: Scalar, index: number) => {
            const translated = displayCategory(context, value);
            if (translated !== String(value ?? "")) return translated;
            return typeof previous === "function"
              ? previous(value, index)
              : typeof previous === "string"
                ? previous.replaceAll("{value}", String(value))
                : value;
          },
        },
      };
    });
  const legend = array(options.legend).map((item) => ({
    ...object(item),
    ...(context.locale &&
      object(item).selector && {
        selector: array(object(item).selector).map((selector) => {
          const current =
            typeof selector === "string"
              ? { type: selector }
              : object(selector);
          if (
            !["all", "inverse"].includes(String(current.type)) ||
            current.title
          )
            return selector;
          return {
            ...current,
            title: controlMessage(
              context.locale!,
              current.type === "all" ? "legend.all" : "legend.inverse",
            ),
          };
        }),
      }),
    formatter: (name: string) => {
      const categoryName = displayCategory(context, name);
      const translated =
        categoryName !== name ? categoryName : displayLabel(context, name);
      const previous = object(item).formatter;
      const formatted =
        typeof previous === "function"
          ? previous(name)
          : typeof previous === "string"
            ? previous.replaceAll("{name}", name)
            : name;
      return translated === name
        ? formatted
        : typeof formatted === "string" && formatted.includes(name)
          ? formatted.split(name).join(translated)
          : translated;
    },
  }));
  const tooltip = object(options.tooltip);
  const previousTooltip = tooltip.formatter;
  const formattedTooltip =
    typeof previousTooltip === "function"
      ? (params: unknown, ...args: unknown[]) => {
          // Translate only escaped text nodes returned by the existing formatter.
          // Keys, callbacks, filters and source params are never changed.
          const formatted = previousTooltip(params, ...args);
          if (typeof formatted !== "string") return formatted;
          const replacements = new Map<string, string>();
          for (const item of array(params)) {
            const param = object(item);
            for (const name of [param.name, param.seriesName])
              if (typeof name === "string") {
                const translated = displayCategory(context, name);
                replacements.set(
                  name,
                  translated !== name
                    ? translated
                    : displayLabel(context, name),
                );
              }
          }
          for (const resource of [
            context.dataset,
            context.chart,
            context.instance,
          ])
            for (const field of resource?.fields || []) {
              if (field.target && resource?.translations[field.key]?.text)
                replacements.set(
                  field.source,
                  resource.translations[field.key].text!,
                );
            }
          return formatted
            .split(/(<[^>]*>)/g)
            .map((part) =>
              part.startsWith("<")
                ? part
                : Array.from(replacements).reduce(
                    (text, [source, translated]) =>
                      source
                        ? text
                            .split(escapeHtml(source))
                            .join(escapeHtml(translated))
                        : text,
                    part,
                  ),
            )
            .join("");
        }
      : previousTooltip;
  const horizontal = context.sourceControls?.orientation === "horizontal";
  return {
    ...raw,
    echartOptions: {
      ...options,
      series,
      ...(context.locale &&
        options.graphic && {
          graphic: array(options.graphic).map((item) => {
            const graphic = object(item);
            const style = object(graphic.style);
            return typeof style.text === "string"
              ? {
                  ...graphic,
                  style: {
                    ...style,
                    text: localizeTotal(
                      context.locale!,
                      style.text,
                      context.nativeTotalTemplate,
                    ),
                  },
                }
              : item;
          }),
        }),
      ...(options.legend && { legend }),
      ...(options.xAxis && {
        xAxis: axis(
          options.xAxis,
          horizontal ? "y_axis_title" : "x_axis_title",
        ),
      }),
      ...(options.yAxis && {
        yAxis: axis(
          options.yAxis,
          horizontal ? "x_axis_title" : "y_axis_title",
        ),
      }),
      tooltip: { ...tooltip, formatter: formattedTooltip },
    },
  };
}
function localizeTable(raw: ObjectValue, context: Presentation): ObjectValue {
  return {
    ...raw,
    columns: array(raw.columns).map((item) => {
      const column = object(item);
      const key = String(column.key ?? column.name ?? "");
      const previous = column.formatter;
      const config = object(column.config);
      const originalLabel = String(
        config.customColumnName ?? column.label ?? key,
      );
      let translatedLabel =
        typeof config.customColumnName === "string"
          ? originalLabel
          : label(context.dataset, key, originalLabel);
      for (const resource of [context.chart, context.instance]) {
        const field = resource?.fields.find(
          (item) => item.key === `column/${key}`,
        );
        if (
          field?.source === originalLabel &&
          resource?.translations[field.key]?.text
        )
          translatedLabel = resource.translations[field.key].text!;
      }
      return {
        ...column,
        label: translatedLabel,
        ...(typeof config.customColumnName === "string" && {
          config: { ...config, customColumnName: translatedLabel },
        }),
        formatter: (value: Scalar, ...args: unknown[]) => {
          const translated = displayCategory(context, value, key);
          if (translated !== String(value ?? "")) return translated;
          return typeof previous === "function"
            ? previous(value, ...args)
            : value;
        },
      };
    }),
  };
}
function localizeSelect(raw: ObjectValue, context: Presentation): ObjectValue {
  return {
    ...raw,
    options: array(raw.options).map((item) => {
      const option = object(item);
      const value = option.value as Scalar;
      return { ...option, label: displayCategory(context, value) };
    }),
  };
}
