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
import { ComponentProps, forwardRef, useEffect, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import NativeHeader from "focalbi-native/SliceHeader";
import {
  Button,
  Checkbox,
  Input,
  Popover,
  Select,
  Space,
} from "@superset-ui/core/components";
import type { RootState } from "src/dashboard/types";
import { updateComponents } from "src/dashboard/actions/dashboardLayout";
import {
  capabilities,
  readSettings,
  selectionTitle,
  PresentationSettings,
} from "./settings";

type Props = ComponentProps<typeof NativeHeader>;

/** Use selections recorded with the successful native request, not filter drafts. */
function requestSelection(
  chart: RootState["charts"][number],
  column: string,
): unknown[] {
  const formData = chart.latestQueryFormData as {
    extra_form_data?: {
      filters?: { col: unknown; op: string; val: unknown }[];
    };
  };
  const filter = formData.extra_form_data?.filters?.find(
    (item) => item.col === column && item.op === "IN",
  );
  return Array.isArray(filter?.val) ? filter.val : [];
}

/** Keep native links, editing and controls; replace only the displayed title. */
const SliceHeader = forwardRef<HTMLDivElement, Props>((props, ref) => {
  const dispatch = useDispatch();
  const item = useSelector((state: RootState) =>
    Object.values(state.dashboardLayout.present).find(
      (item) => item.meta?.chartId === props.slice.slice_id,
    ),
  );
  const filters = useSelector(
    (state: RootState) => state.nativeFilters.filters,
  );
  const chart = useSelector(
    (state: RootState) => state.charts[props.slice.slice_id],
  );
  const settings = readSettings(item?.meta.focalbi_rendering);
  const binding = settings?.title && filters[settings.title.filterId];
  const column =
    binding && "targets" in binding
      ? binding.targets[0]?.column?.name
      : undefined;
  const inScope =
    binding &&
    "chartsInScope" in binding &&
    binding.chartsInScope?.includes(props.slice.slice_id);
  const [title, setTitle] = useState(props.sliceName || "");
  const appliedSelection = useRef<unknown[]>([]);
  useEffect(() => {
    if (!settings?.title || !column || !inScope) {
      setTitle(props.sliceName || "");
      return;
    }
    if (chart && ["success", "rendered"].includes(chart.chartStatus)) {
      appliedSelection.current = requestSelection(chart, column);
    }
    setTitle(
      selectionTitle(
        settings.title,
        appliedSelection.current,
        props.sliceName || "",
      ),
    );
  }, [
    chart?.queriesResponse,
    chart?.chartStatus,
    column,
    inScope,
    props.sliceName,
    settings?.title?.filterId,
    settings?.title?.single,
    settings?.title?.multiple,
  ]);

  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<PresentationSettings>({ version: 1 });
  const available = Object.values(filters).filter(
    (filter) =>
      "targets" in filter &&
      "chartsInScope" in filter &&
      filter.chartsInScope?.includes(props.slice.slice_id),
  );
  const content = (
    <Space direction="vertical" style={{ width: 340 }}>
      <strong>FocalBI presentation</strong>
      <label>Title selection filter</label>
      <Select
        aria-label="Title selection filter"
        style={{ width: "100%" }}
        allowClear
        value={draft.title?.filterId}
        options={available.map((filter) => ({
          value: filter.id,
          label: filter.name,
        }))}
        onChange={(filterId: string | undefined) =>
          setDraft({
            ...draft,
            title: filterId
              ? {
                  filterId,
                  single:
                    draft.title?.single ||
                    "{selection} " + (props.sliceName || ""),
                  multiple: draft.title?.multiple || props.sliceName || "",
                }
              : undefined,
          })
        }
      />
      {draft.title && (
        <>
          <label>Single selection title — use {"{selection}"}</label>
          <Input
            aria-label="Single selection title"
            value={draft.title.single}
            onChange={(event) =>
              setDraft({
                ...draft,
                title: { ...draft.title!, single: event.target.value },
              })
            }
          />
          <label>Multiple selections title</label>
          <Input
            aria-label="Multiple selections title"
            value={draft.title.multiple}
            onChange={(event) =>
              setDraft({
                ...draft,
                title: { ...draft.title!, multiple: event.target.value },
              })
            }
          />
        </>
      )}
      {capabilities[props.slice.viz_type]?.highlight && (
        <>
          <label>Selection highlighting filter</label>
          <Select
            aria-label="Selection highlighting filter"
            style={{ width: "100%" }}
            allowClear
            value={draft.highlight?.filterId}
            options={Object.values(filters)
              .filter((filter) => "targets" in filter)
              .map((filter) => ({ value: filter.id, label: filter.name }))}
            onChange={(filterId: string | undefined) =>
              setDraft({
                ...draft,
                highlight: filterId
                  ? {
                      filterId,
                      dimension: draft.highlight?.dimension || "",
                      selectedColors: draft.highlight?.selectedColors || [
                        "#66B3E1",
                        "#318AC2",
                        "#79C7B0",
                        "#EEA746",
                        "#9367B4",
                      ],
                      otherColor: draft.highlight?.otherColor || "#142D59",
                      labelColors: draft.highlight?.labelColors,
                    }
                  : undefined,
              })
            }
          />
          {draft.highlight && (
            <>
              <label>Result dimension for highlighting</label>
              <Input
                aria-label="Highlight dimension"
                value={draft.highlight.dimension}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    highlight: {
                      ...draft.highlight!,
                      dimension: event.target.value,
                    },
                  })
                }
              />
              <label>Peer color</label>
              <Input
                aria-label="Peer color"
                value={draft.highlight.otherColor}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    highlight: {
                      ...draft.highlight!,
                      otherColor: event.target.value,
                    },
                  })
                }
              />
            </>
          )}
        </>
      )}
      {capabilities[props.slice.viz_type]?.layering && (
        <Checkbox
          checked={draft.secondaryBehindPrimary}
          onChange={(event) =>
            setDraft({ ...draft, secondaryBehindPrimary: event.target.checked })
          }
        >
          Place secondary series behind primary series
        </Checkbox>
      )}
      {item?.meta.focalbi_rendering && !settings && (
        <span role="alert">
          Invalid presentation settings; native presentation is used.
        </span>
      )}
      {settings?.title && !inScope && (
        <span role="alert">
          Title filter is missing or outside this chart’s scope.
        </span>
      )}
      <Button
        disabled={!readSettings(draft)}
        onClick={() => {
          if (!item || !readSettings(draft)) return;
          dispatch(
            updateComponents({
              [item.id]: {
                ...item,
                meta: { ...item.meta, focalbi_rendering: draft },
              },
            }),
          );
          setOpen(false);
        }}
      >
        Apply presentation settings
      </Button>
      <span>
        Use the dashboard’s Save or Discard controls to keep or undo these
        settings.
      </span>
    </Space>
  );
  return (
    <div data-test="focalbi-chart-header" style={{ position: "relative" }}>
      <NativeHeader
        {...props}
        ref={ref}
        sliceName={props.editMode ? props.sliceName : title}
      />
      {props.editMode && (
        <Popover
          content={content}
          trigger="click"
          open={open}
          onOpenChange={(value) => {
            setOpen(value);
            if (value) setDraft(settings || { version: 1 });
          }}
        >
          <Button
            size="small"
            aria-label="FocalBI presentation settings"
            style={{ marginBottom: 4 }}
          >
            Presentation
          </Button>
        </Popover>
      )}
    </div>
  );
});
export default SliceHeader;
