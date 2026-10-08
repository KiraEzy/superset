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
import { useRef } from "react";
import { t, tn } from "@apache-superset/core/translation";
import { Input, Select, Space } from "@superset-ui/core/components";
import type {
  SearchInputProps,
  SelectPageSizeRendererProps,
} from "focalbi-native/DataTable";
import { useControlMessages } from "./ControlMessages";

export function SearchInput({
  count,
  value,
  onChange,
  onBlur,
  inputRef,
}: SearchInputProps) {
  const ui = useControlMessages();
  return (
    <Space direction="horizontal" size={4} className="dt-global-filter">
      {ui("table.search", t("Search"))}
      <Input
        aria-label={ui("table.searchRecords", t("Search %s records", count), {
          count,
        })}
        placeholder={ui(
          count === 1 ? "table.record" : "table.records",
          tn("%s record...", "%s records...", count, count),
          { count },
        )}
        value={value}
        onChange={onChange}
        onBlur={onBlur}
        ref={inputRef}
      />
    </Space>
  );
}
export function SelectPageSize({
  current,
  options,
  onChange,
}: SelectPageSizeRendererProps) {
  const ui = useControlMessages();
  const id = useRef(
    `focalbi-page-size-${Math.random().toString(36).slice(2)}`,
  ).current;
  return (
    <Space direction="horizontal" size={4} className="dt-select-page-size">
      {ui("table.show", t("Show"))}
      <Select<number>
        id={id}
        value={current}
        size="small"
        style={{ width: 72 }}
        aria-label={ui("table.showPerPage", t("Show entries per page"))}
        onChange={onChange}
        options={options.map((option) => {
          const [size, text] = Array.isArray(option)
            ? option
            : [option, option];
          const nativeAll = [t("All"), t("all"), "All", "all"];
          return {
            value: Number(size),
            label:
              size === 0 && nativeAll.includes(String(text))
                ? ui("table.all", String(text))
                : text,
            "aria-label": ui(
              "table.showEntries",
              t("Show %s entries", size === 0 ? t("all") : size),
              { count: size === 0 ? ui("table.all", t("all")) : size },
            ),
          };
        })}
      />
      {ui("table.perPage", t("entries per page"))}
    </Space>
  );
}
