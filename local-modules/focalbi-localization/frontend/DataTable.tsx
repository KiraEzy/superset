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
import { useContext, useMemo, useRef } from "react";
import HostTable from "focalbi-host/DataTable";
import { DataTableProps } from "focalbi-native/DataTable";
import { NativeQueryContext, useLocalization } from "./runtime";
import { TableDisplayState } from "./tableState";
import { t } from "@apache-superset/core/translation";
import { useControlMessages } from "./ControlMessages";
import { SearchInput, SelectPageSize } from "./TableControls";
export * from "focalbi-native/DataTable";

export default function DataTable<D extends object>(props: DataTableProps<D>) {
  const runtime = useLocalization();
  const ui = useControlMessages();
  const query = useContext(NativeQueryContext);
  const display = useMemo(() => ({}), [runtime?.bundle, runtime?.locale]);
  const saved = useRef(new TableDisplayState());
  const columns = JSON.stringify(
    props.columns.map((column, index) => {
      const identity = column as {
        columnKey?: string;
        id?: string;
        accessor?: unknown;
      };
      return (
        identity.columnKey ??
        identity.id ??
        (typeof identity.accessor === "string" ? identity.accessor : index)
      );
    }),
  );
  saved.current.update(display, query, columns);
  const reducer: NonNullable<DataTableProps<D>["stateReducer"]> = (
    state,
    action,
    previous,
    instance,
  ) => {
    const native =
      props.stateReducer?.(state, action, previous, instance) || state;
    return saved.current.reduce(native, previous, action, props.pageSize);
  };
  return (
    <HostTable<D>
      {...props}
      searchInput={
        runtime &&
        props.searchInput !== false &&
        (!props.searchInput || props.searchInput === true)
          ? SearchInput
          : props.searchInput
      }
      selectPageSize={
        runtime &&
        props.selectPageSize !== false &&
        (!props.selectPageSize || props.selectPageSize === true)
          ? SelectPageSize
          : props.selectPageSize
      }
      noResults={
        runtime
          ? (filter) => {
              const original =
                typeof props.noResults === "function"
                  ? props.noResults(filter)
                  : props.noResults;
              const native = t(
                filter ? "No matching records found" : "No records found",
              );
              return !original || original === native
                ? ui(filter ? "table.noMatching" : "table.noRecords", native)
                : original;
            }
          : props.noResults
      }
      stateReducer={
        !props.serverPagination && runtime && query
          ? reducer
          : props.stateReducer
      }
    />
  );
}
