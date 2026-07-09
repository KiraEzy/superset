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
import { t } from '@apache-superset/core/translation';
import { useToasts } from 'src/components/MessageToasts/withToasts';
import { ModalTitleWithIcon } from 'src/components/ModalTitleWithIcon';
import { Actions } from 'src/constants';
import {
  FormItem,
  FormModal,
  Input,
  Select,
  AsyncSelect,
} from '@superset-ui/core/components';
import { fetchUserOptions } from 'src/features/groups/utils';
import { FormValues, PostModalProps } from './types';
import { createPost, updatePost } from './api';

function PostModal({
  show,
  onHide,
  onSave,
  roles,
  isEditMode = false,
  post,
}: PostModalProps) {
  const { addDangerToast, addSuccessToast } = useToasts();

  const handleFormSubmit = async (values: FormValues) => {
    const handleError = async (
      err: Response,
      action: Actions.CREATE | Actions.UPDATE,
    ) => {
      let errorMessage =
        action === Actions.CREATE
          ? t('There was an error creating the post. Please, try again.')
          : t('There was an error updating the post. Please, try again.');
      if (err.status === 422) {
        const errorData = await err.json();
        if (errorData?.message) {
          errorMessage = errorData.message;
        }
      }
      addDangerToast(errorMessage);
      throw err;
    };

    if (isEditMode) {
      if (!post) {
        throw new Error('Post is required in edit mode');
      }
      try {
        await updatePost(post.id, values);
        addSuccessToast(t('The post has been updated successfully.'));
      } catch (err) {
        await handleError(err, Actions.UPDATE);
      }
    } else {
      try {
        await createPost(values);
        addSuccessToast(t('The post has been created successfully.'));
      } catch (err) {
        await handleError(err, Actions.CREATE);
      }
    }
  };

  const requiredFields = ['name'];
  const initialValues = {
    name: post?.name,
    label: post?.label,
    description: post?.description,
    roles: post?.role_ids || [],
    users:
      post?.users?.map(user => ({
        value: user.id,
        label: user.username,
      })) || [],
  };

  return (
    <FormModal
      show={show}
      onHide={onHide}
      name={isEditMode ? 'Edit Post' : 'Add Post'}
      title={
        <ModalTitleWithIcon
          isEditMode={isEditMode}
          title={isEditMode ? t('Edit Post') : t('Add Post')}
        />
      }
      onSave={onSave}
      formSubmitHandler={handleFormSubmit}
      requiredFields={requiredFields}
      initialValues={initialValues}
    >
      <FormItem
        name="name"
        label={t('Name')}
        rules={[{ required: true, message: t('Name is required') }]}
      >
        <Input name="name" placeholder={t("Enter the post's name")} />
      </FormItem>
      <FormItem name="label" label={t('Label')}>
        <Input name="label" placeholder={t("Enter the post's label")} />
      </FormItem>
      <FormItem name="description" label={t('Description')}>
        <Input
          name="description"
          placeholder={t("Enter the post's description")}
        />
      </FormItem>
      <FormItem name="roles" label={t('Roles')}>
        <Select
          name="roles"
          mode="multiple"
          placeholder={t('Select roles granted by this post')}
          options={roles.map(role => ({
            value: role.id,
            label: role.name,
          }))}
          getPopupContainer={trigger => trigger.closest('.ant-modal-content')}
        />
      </FormItem>
      <FormItem name="users" label={t('Users')}>
        <AsyncSelect
          name="users"
          mode="multiple"
          placeholder={t('Assign users to this post')}
          options={(filterValue, page, pageSize) =>
            fetchUserOptions(filterValue, page, pageSize, addDangerToast)
          }
        />
      </FormItem>
    </FormModal>
  );
}

export const PostAddModal = (
  props: Omit<PostModalProps, 'isEditMode' | 'post'>,
) => <PostModal {...props} isEditMode={false} />;

export const PostEditModal = (
  props: Omit<PostModalProps, 'isEditMode'> & { post: PostModalProps['post'] },
) => <PostModal {...props} isEditMode />;

export default PostModal;
