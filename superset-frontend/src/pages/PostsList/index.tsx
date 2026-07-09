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
import { useCallback, useEffect, useMemo, useState } from 'react';
import { t } from '@apache-superset/core/translation';
import SubMenu, { SubMenuProps } from 'src/features/home/SubMenu';
import { ActionsBar, ActionProps } from 'src/components/ListView/ActionsBar';
import { isUserAdmin } from 'src/dashboard/util/permissionUtils';
import { useToasts } from 'src/components/MessageToasts/withToasts';
import { fetchPaginatedData } from 'src/utils/fetchOptions';
import {
  Table,
  Icons,
  DeleteModal,
  type ColumnsType,
} from '@superset-ui/core/components';
import { PostAddModal, PostEditModal } from 'src/features/posts/PostModal';
import { deletePost, fetchPosts } from 'src/features/posts/api';
import { PostObject, Role } from 'src/features/posts/types';

interface PostsListProps {
  user: {
    userId: string | number;
    firstName: string;
    lastName: string;
    roles: object;
  };
}

enum ModalType {
  ADD = 'add',
  EDIT = 'edit',
}

function PostsList({ user }: PostsListProps) {
  const { addDangerToast, addSuccessToast } = useToasts();
  const isAdmin = useMemo(() => isUserAdmin(user), [user]);

  const [posts, setPosts] = useState<PostObject[]>([]);
  const [loading, setLoading] = useState(true);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loadingState, setLoadingState] = useState({ roles: true });
  const [modalState, setModalState] = useState({ edit: false, add: false });
  const [currentPost, setCurrentPost] = useState<PostObject | null>(null);
  const [postDeleting, setPostDeleting] = useState<PostObject | null>(null);

  const openModal = (type: ModalType) =>
    setModalState(prev => ({ ...prev, [type]: true }));
  const closeModal = (type: ModalType) =>
    setModalState(prev => ({ ...prev, [type]: false }));

  const loadPosts = useCallback(() => {
    setLoading(true);
    fetchPosts()
      .then(setPosts)
      .catch(() => addDangerToast(t('There was an error fetching posts')))
      .finally(() => setLoading(false));
  }, [addDangerToast]);

  const fetchRoles = useCallback(() => {
    fetchPaginatedData({
      endpoint: '/api/v1/security/roles/',
      setData: setRoles,
      setLoadingState,
      loadingKey: 'roles',
      addDangerToast,
      errorMessage: t('Error while fetching roles'),
    });
  }, [addDangerToast]);

  useEffect(() => {
    loadPosts();
    fetchRoles();
  }, [loadPosts, fetchRoles]);

  const handleDelete = async (post: PostObject) => {
    try {
      await deletePost(post.id);
      addSuccessToast(t('Deleted post: %s', post.name));
      setPostDeleting(null);
      loadPosts();
    } catch (error) {
      addDangerToast(t('There was an issue deleting %s', post.name));
    }
  };

  const columns: ColumnsType<PostObject> = useMemo(
    () => [
      {
        title: t('Name'),
        dataIndex: 'name',
        key: 'name',
      },
      {
        title: t('Label'),
        dataIndex: 'label',
        key: 'label',
      },
      {
        title: t('Roles'),
        key: 'roles',
        render: (_: unknown, record: PostObject) =>
          record.role_names?.join(', ') || t('No roles'),
      },
      {
        title: t('Users'),
        key: 'users',
        render: (_: unknown, record: PostObject) => record.user_count,
      },
      {
        title: t('Actions'),
        key: 'actions',
        width: 120,
        render: (_: unknown, record: PostObject) => {
          if (!isAdmin) {
            return null;
          }
          const actions = [
            {
              label: 'post-list-edit-action',
              tooltip: t('Edit post'),
              placement: 'bottom',
              icon: 'EditOutlined',
              onClick: () => {
                setCurrentPost(record);
                openModal(ModalType.EDIT);
              },
            },
            {
              label: 'post-list-delete-action',
              tooltip: t('Delete post'),
              placement: 'bottom',
              icon: 'DeleteOutlined',
              onClick: () => setPostDeleting(record),
            },
          ];
          return <ActionsBar actions={actions as ActionProps[]} />;
        },
      },
    ],
    [isAdmin],
  );

  const subMenuButtons: SubMenuProps['buttons'] = [];
  if (isAdmin) {
    subMenuButtons.push({
      name: t('Post'),
      icon: <Icons.PlusOutlined iconSize="m" />,
      buttonStyle: 'primary',
      onClick: () => openModal(ModalType.ADD),
      loading: loadingState.roles,
      'data-test': 'add-post-button',
    });
  }

  return (
    <>
      <SubMenu name={t('List Posts')} buttons={subMenuButtons} />
      <PostAddModal
        show={modalState.add}
        onHide={() => closeModal(ModalType.ADD)}
        onSave={() => {
          loadPosts();
          closeModal(ModalType.ADD);
        }}
        roles={roles}
      />
      {modalState.edit && currentPost && (
        <PostEditModal
          post={currentPost}
          show={modalState.edit}
          onHide={() => closeModal(ModalType.EDIT)}
          onSave={() => {
            loadPosts();
            closeModal(ModalType.EDIT);
          }}
          roles={roles}
        />
      )}
      {postDeleting && (
        <DeleteModal
          description={t('This action will permanently delete the post.')}
          onConfirm={() => handleDelete(postDeleting)}
          onHide={() => setPostDeleting(null)}
          open
          title={t('Delete Post?')}
        />
      )}
      <Table<PostObject>
        columns={columns}
        data={posts}
        loading={loading}
        rowKey="id"
        usePagination
        defaultPageSize={25}
      />
    </>
  );
}

export default PostsList;
