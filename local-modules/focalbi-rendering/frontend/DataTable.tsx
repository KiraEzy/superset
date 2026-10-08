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
import { useContext, useMemo, useRef } from "react";
import NativeTable, { DataTableProps } from "focalbi-native/DataTable";
import type { TableState } from "react-table";
import { TableStateContext } from "./context";
export * from "focalbi-native/DataTable";

/** Preserve native client table interactions when changing renderer components. */
export default function DataTable<D extends object>(props: DataTableProps<D>) {
  const saved = useContext(TableStateContext);
  const mountedQuery = useRef(saved?.current.query);
  const restoring = useRef(Boolean(saved?.current.state));
  const reducer = useMemo(
    () =>
      (
        state: TableState<D>,
        action: { type: string; pageSize?: number },
        previous: TableState<D>,
        instance: Parameters<NonNullable<DataTableProps<D>["stateReducer"]>>[3],
      ) => {
        const nativeState =
          props.stateReducer?.(state, action, previous, instance) || state;
        let next =
          action.type === "init" &&
          saved?.current.state &&
          !props.serverPagination
            ? ({ ...nativeState, ...saved.current.state } as TableState<D>)
            : nativeState;
        if (
          restoring.current &&
          saved?.current.query === mountedQuery.current &&
          ["resetPage", "resetSortBy", "resetGlobalFilter"].includes(
            action.type,
          )
        ) {
          next = {
            ...next,
            pageIndex: previous.pageIndex,
            sortBy: previous.sortBy,
            globalFilter: previous.globalFilter,
          };
        } else if (
          action.type !== "init" &&
          !action.type.startsWith("reset") &&
          action.type !== "setStickyState" &&
          !(action.type === "setPageSize" && action.pageSize === props.pageSize)
        )
          restoring.current = false;
        if (saved && !props.serverPagination)
          saved.current.state = {
            pageIndex: next.pageIndex,
            pageSize: next.pageSize,
            sortBy: next.sortBy,
            globalFilter: next.globalFilter,
            columnOrder: next.columnOrder,
          };
        return next;
      },
    [saved, props.stateReducer, props.serverPagination, props.data],
  );
  if (!saved) return <NativeTable<D> {...props} />;
  return (
    <NativeTable<D>
      {...props}
      initialSearchText={
        !props.serverPagination &&
        typeof saved?.current.state?.globalFilter === "string"
          ? saved.current.state.globalFilter
          : props.initialSearchText
      }
      stateReducer={reducer}
    />
  );
}
