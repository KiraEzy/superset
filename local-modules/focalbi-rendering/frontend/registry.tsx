/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership. The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License. You may obtain a copy of the License at
 * http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import {
  ComponentType,
  lazy,
  Suspense,
  useContext,
  useEffect,
  useMemo,
  useRef,
} from "react";
import { useSelector } from "react-redux";
import {
  ChartProps,
  getChartComponentRegistry,
  getChartTransformPropsRegistry,
} from "@superset-ui/core";
import type { RootState } from "src/dashboard/types";
import {
  RendererContext,
  TableStateContext,
  TableInteractionState,
} from "./context";
import {
  capabilities,
  readSettings,
  selectionColors,
  PresentationSettings,
  Engine,
} from "./settings";
import { observeEchartsInteractions } from "./echarts-interactions";
import type { Interaction } from "./contracts";
import { sortCategoryBars } from "./category-sort";
import baselineNumber from "../vendor/baseline/echarts/BigNumber/BigNumberTotal/transformProps";
import baselinePie from "../vendor/baseline/echarts/Pie/transformProps";
import baselineBar from "../vendor/baseline/echarts/Timeseries/transformProps";
import baselineMixed from "../vendor/baseline/echarts/MixedTimeseries/transformProps";
import baselineTable from "../vendor/baseline/table/transformProps";
import forkNumber from "../vendor/fork/echarts/BigNumber/BigNumberTotal/transformProps";
import forkPie from "../vendor/fork/echarts/Pie/transformProps";
import forkBar from "../vendor/fork/echarts/Timeseries/transformProps";
import forkMixed from "../vendor/fork/echarts/MixedTimeseries/transformProps";
import forkTable from "../vendor/fork/table/transformProps";

type VisualProps = Record<string, unknown>;
type Transform = (props: ChartProps) => VisualProps;
interface Entry {
  transform: Transform;
  Component: ComponentType<VisualProps>;
}
type Loader = () => Promise<{ default: ComponentType<VisualProps> }>;
const entry = (transform: unknown, load: unknown): Entry => ({
  transform: transform as Transform,
  Component: lazy(load as Loader),
});
const bar =
  (transform: unknown): Transform =>
  (props) =>
    sortCategoryBars(
      (transform as Transform)({
        ...props,
        formData: { ...props.formData, seriesType: "bar" },
      }),
      props.formData,
    );

/** Entries contain transform/draw implementations only. Query registries are untouched. */
export const registry: Record<string, Record<Engine, Entry>> = {
  big_number_total: {
    baseline: entry(
      baselineNumber,
      () => import("../vendor/baseline/echarts/BigNumber/BigNumberViz"),
    ),
    fork: entry(
      forkNumber,
      () => import("../vendor/fork/echarts/BigNumber/BigNumberViz"),
    ),
  },
  pie: {
    baseline: entry(
      baselinePie,
      () => import("../vendor/baseline/echarts/Pie/EchartsPie"),
    ),
    fork: entry(forkPie, () => import("../vendor/fork/echarts/Pie/EchartsPie")),
  },
  echarts_timeseries_bar: {
    baseline: entry(
      bar(baselineBar),
      () => import("../vendor/baseline/echarts/Timeseries/EchartsTimeseries"),
    ),
    fork: entry(
      bar(forkBar),
      () => import("../vendor/fork/echarts/Timeseries/EchartsTimeseries"),
    ),
  },
  mixed_timeseries: {
    baseline: entry(
      baselineMixed,
      () =>
        import("../vendor/baseline/echarts/MixedTimeseries/EchartsMixedTimeseries"),
    ),
    fork: entry(
      forkMixed,
      () =>
        import("../vendor/fork/echarts/MixedTimeseries/EchartsMixedTimeseries"),
    ),
  },
  table: {
    baseline: entry(
      baselineTable,
      () => import("../vendor/baseline/table/TableChart"),
    ),
    fork: entry(forkTable, () => import("../vendor/fork/table/TableChart")),
  },
};

export const renderKey = (type: string) => `focalbi.render/${type}`;

type Datum = {
  name?: string;
  value?: unknown;
  itemStyle?: Record<string, unknown>;
};
type Series = {
  type?: string;
  yAxisIndex?: number;
  z?: number;
  data?: (Datum | unknown[])[];
  itemStyle?: Record<string, unknown>;
};
type Axis = { type?: string; data?: (string | { value: string })[] };

/** Decorate options without altering returned values, grouping, ranking or ratios. */
export function decorate(
  props: VisualProps,
  settings: PresentationSettings | undefined,
  selected: unknown[],
): VisualProps {
  if (!props.echartOptions || !settings) return props;
  const options = props.echartOptions as {
    series?: Series[];
    xAxis?: Axis | Axis[];
    yAxis?: Axis | Axis[];
  };
  const series = options.series?.map((series) => ({
    ...series,
    data: series.data?.map((datum) =>
      Array.isArray(datum) ? [...datum] : { ...datum },
    ),
  }));
  const highlight = settings.highlight;
  if (highlight && series) {
    const colors = selectionColors(selected, highlight);
    const axes = [...[options.xAxis].flat(), ...[options.yAxis].flat()].filter(
      Boolean,
    ) as Axis[];
    const categories = axes.find((axis) => axis.type === "category")?.data;
    series.forEach((serie) => {
      if (serie.type !== "pie" && serie.type !== "bar") return;
      serie.data = serie.data?.map((datum, index) => {
        const category = categories?.[index];
        const name =
          !Array.isArray(datum) && datum.name
            ? datum.name
            : typeof category === "string"
              ? category
              : (category?.value ??
                (Array.isArray(datum)
                  ? datum.find((value) => typeof value === "string")
                  : undefined));
        if (name === undefined) return datum;
        return {
          ...(Array.isArray(datum) ? { value: datum } : datum),
          itemStyle: {
            ...(!Array.isArray(datum) ? datum.itemStyle : undefined),
            color: colors.get(String(name)) || highlight.otherColor,
          },
        };
      });
    });
  }
  if (settings.secondaryBehindPrimary && series) {
    series.forEach((serie) => {
      serie.z = serie.yAxisIndex === 1 ? 1 : 2;
    });
  }
  return { ...props, echartOptions: { ...options, series } };
}

interface Envelope {
  raw: ChartProps;
  post?: (props: VisualProps) => VisualProps;
}

/** Use native result inputs in a stable host; retain interaction state across engines. */
function Renderer({ type, raw, post }: Envelope & { type: string }) {
  const engine = useContext(RendererContext) || "baseline";
  const selectedEntry = registry[type][engine];
  const element = useRef<HTMLDivElement>(null);
  const interaction = useRef<Interaction>({});
  const tableState = useRef<TableInteractionState>({});
  const sourceQuery = raw.queriesData[0];
  if (tableState.current.query !== sourceQuery)
    tableState.current = { query: sourceQuery };
  const chartId = Number(raw.rawFormData.slice_id);
  const settings = useSelector((state: RootState) => {
    const item = Object.values(state.dashboardLayout.present).find(
      (item) => item.meta?.chartId === chartId,
    );
    return item?.meta.focalbi_rendering;
  });
  const presentation = useMemo(() => readSettings(settings), [settings]);
  const selected = useSelector((state: RootState) =>
    presentation?.highlight
      ? state.dataMask[presentation.highlight.filterId]?.filterState?.value
      : undefined,
  );
  const dimension = presentation?.highlight?.dimension;
  const hasDimension = Boolean(
    dimension &&
    raw.queriesData.some((query) => query.colnames?.includes(dimension)),
  );
  const highlightAvailable = capabilities[type].highlight && hasDimension;
  const transformed = useMemo(() => {
    const native = selectedEntry.transform(raw);
    const applicable = presentation && {
      ...presentation,
      highlight: highlightAvailable ? presentation.highlight : undefined,
      secondaryBehindPrimary: capabilities[type].layering
        ? presentation.secondaryBehindPrimary
        : undefined,
    };
    return decorate(
      post ? post(native) : native,
      applicable,
      Array.isArray(selected) ? selected : [],
    );
  }, [selectedEntry, raw, post, presentation, selected, highlightAvailable]);
  useEffect(
    () =>
      element.current
        ? observeEchartsInteractions(element.current, () => interaction.current)
        : undefined,
    [engine],
  );
  const Component = selectedEntry.Component;
  return (
    <div
      ref={element}
      data-test="focalbi-chart"
      data-renderer={engine}
      data-viz-type={type}
    >
      {settings && !presentation && (
        <span role="alert">
          Invalid presentation settings; native presentation is used.
        </span>
      )}
      {presentation?.highlight && !highlightAvailable && (
        <span role="alert">
          Selection highlighting requires a supported chart and the configured
          result dimension.
        </span>
      )}
      {presentation?.secondaryBehindPrimary && !capabilities[type].layering && (
        <span role="alert">
          Series layering is unavailable for this renderer type.
        </span>
      )}
      <TableStateContext.Provider value={tableState}>
        <Suspense fallback={null}>
          <Component {...transformed} />
        </Suspense>
      </TableStateContext.Provider>
    </div>
  );
}

/** Register rendering-only names; never register replacement query builders. */
export default function setupRenderers() {
  for (const type of Object.keys(registry)) {
    getChartTransformPropsRegistry().registerValue(
      renderKey(type),
      (raw: ChartProps) => ({ raw }),
    );
    getChartComponentRegistry().registerValue(
      renderKey(type),
      (props: Envelope) => <Renderer {...props} type={type} />,
    );
  }
}
