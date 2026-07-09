/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { RoleObject } from 'src/pages/RolesList';
import { FormModal, FormInstance, Icons } from '@superset-ui/core/components';
import {
  BaseModalProps,
  RoleForm,
  SelectOption,
} from 'src/features/roles/types';
import { useToasts } from 'src/components/MessageToasts/withToasts';
import { fetchPaginatedData } from 'src/utils/fetchOptions';
import { ModalTitleWithIcon } from 'src/components/ModalTitleWithIcon';
import { GroupsField, PermissionsField, RoleNameField } from './RoleFormItems';
import {
  fetchPermissionsByIds,
  updateRoleGroups,
  updateRoleName,
  updateRolePermissions,
} from './utils';

export interface RoleListEditModalProps extends BaseModalProps {
  role: RoleObject;
}

// Under post-based RBAC, users are never attached to roles directly (they get
// roles through Posts), so the role editor no longer exposes a Users tab/field.
function RoleListEditModal({
  show,
  onHide,
  role,
  onSave,
}: RoleListEditModalProps) {
  const { id, name, permission_ids = [], group_ids = [] } = role;
  const stablePermissionIds = useMemo(
    () => permission_ids,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(permission_ids)],
  );
  const stableGroupIds = useMemo(
    () => group_ids,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(group_ids)],
  );
  const { addDangerToast, addSuccessToast } = useToasts();
  const [rolePermissions, setRolePermissions] = useState<SelectOption[]>([]);
  const [roleGroups, setRoleGroups] = useState<SelectOption[]>([]);
  const [loadingRolePermissions, setLoadingRolePermissions] = useState(true);
  const [loadingRoleGroups, setLoadingRoleGroups] = useState(true);
  const formRef = useRef<FormInstance | null>(null);
  const permissionFetchSucceeded = useRef(false);
  const groupFetchSucceeded = useRef(false);

  useEffect(() => {
    if (!stablePermissionIds.length) {
      setRolePermissions([]);
      setLoadingRolePermissions(false);
      return;
    }

    setLoadingRolePermissions(true);
    permissionFetchSucceeded.current = false;

    fetchPermissionsByIds(stablePermissionIds)
      .then(data => {
        permissionFetchSucceeded.current = true;
        setRolePermissions(data);
      })
      .catch(() => {
        addDangerToast(t('There was an error loading permissions.'));
      })
      .finally(() => {
        setLoadingRolePermissions(false);
      });
  }, [addDangerToast, id, stablePermissionIds]);

  useEffect(() => {
    if (!stableGroupIds.length) {
      setRoleGroups([]);
      setLoadingRoleGroups(false);
      return;
    }

    setLoadingRoleGroups(true);
    groupFetchSucceeded.current = false;
    const filters = [{ col: 'id', opr: 'in', value: stableGroupIds }];

    fetchPaginatedData({
      endpoint: `/api/v1/security/groups/`,
      pageSize: 100,
      setData: (data: SelectOption[]) => {
        groupFetchSucceeded.current = true;
        setRoleGroups(data);
      },
      filters,
      setLoadingState: (loading: boolean) => setLoadingRoleGroups(loading),
      loadingKey: 'roleGroups',
      addDangerToast,
      errorMessage: t('There was an error loading groups.'),
      mapResult: (group: { id: number; name: string }) => ({
        value: group.id,
        label: group.name,
      }),
    });
  }, [addDangerToast, stableGroupIds, id]);

  useEffect(() => {
    if (
      !loadingRolePermissions &&
      formRef.current &&
      stablePermissionIds.length > 0
    ) {
      const fetchedIds = new Set(rolePermissions.map(p => p.value));
      const missingIds = stablePermissionIds.filter(id => !fetchedIds.has(id));
      const allPermissions = [
        ...rolePermissions,
        ...missingIds.map(id => ({ value: id, label: String(id) })),
      ];
      if (missingIds.length > 0 && permissionFetchSucceeded.current) {
        addDangerToast(
          t('Some permissions could not be resolved and are shown as IDs.'),
        );
      }
      formRef.current.setFieldsValue({
        rolePermissions: allPermissions,
      });
    }
  }, [
    loadingRolePermissions,
    rolePermissions,
    stablePermissionIds,
    addDangerToast,
  ]);

  useEffect(() => {
    if (!loadingRoleGroups && formRef.current && stableGroupIds.length > 0) {
      const fetchedIds = new Set(roleGroups.map(g => g.value));
      const missingIds = stableGroupIds.filter(id => !fetchedIds.has(id));
      const allGroups = [
        ...roleGroups,
        ...missingIds.map(id => ({ value: id, label: String(id) })),
      ];
      if (missingIds.length > 0 && groupFetchSucceeded.current) {
        addDangerToast(
          t('Some groups could not be resolved and are shown as IDs.'),
        );
      }
      formRef.current.setFieldsValue({
        roleGroups: allGroups,
      });
    }
  }, [loadingRoleGroups, roleGroups, stableGroupIds, addDangerToast]);

  const mapSelectedIds = (options?: Array<SelectOption | number>) =>
    options?.map(option =>
      typeof option === 'number' ? option : option.value,
    ) || [];

  const handleFormSubmit = async (values: RoleForm) => {
    try {
      const permissionIds = mapSelectedIds(values.rolePermissions);
      const groupIds = mapSelectedIds(values.roleGroups);
      await Promise.all([
        updateRoleName(id, values.roleName),
        updateRolePermissions(id, permissionIds),
        updateRoleGroups(id, groupIds),
      ]);
      addSuccessToast(t('The role has been updated successfully.'));
    } catch (err) {
      addDangerToast(
        t('There was an error updating the role. Please, try again.'),
      );
      throw err;
    }
  };

  const initialValues = {
    roleName: name,
    rolePermissions: permission_ids.map(permissionId => ({
      value: permissionId,
      label: String(permissionId),
    })),
    roleGroups: group_ids.map(groupId => ({
      value: groupId,
      label: String(groupId),
    })),
  };

  return (
    <FormModal
      show={show}
      onHide={onHide}
      name="Edit Role"
      title={
        <ModalTitleWithIcon
          title={t('Edit Role')}
          icon={<Icons.EditOutlined />}
        />
      }
      onSave={onSave}
      formSubmitHandler={handleFormSubmit}
      initialValues={initialValues}
      requiredFields={['roleName']}
    >
      {(form: FormInstance) => {
        formRef.current = form;

        return (
          <>
            <RoleNameField />
            <PermissionsField
              addDangerToast={addDangerToast}
              loading={loadingRolePermissions}
            />
            <GroupsField
              addDangerToast={addDangerToast}
              loading={loadingRoleGroups}
            />
          </>
        );
      }}
    </FormModal>
  );
}

export default RoleListEditModal;
