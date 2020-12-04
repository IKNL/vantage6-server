# -*- coding: utf-8 -*-
import json
import logging

from flask import request, g
from flask_restful import reqparse
from flasgger import swag_from
from http import HTTPStatus
from pathlib import Path

from vantage6.server import db
from vantage6.server.permission import (
    Scope as S,
    Operation as P,
    PermissionManager
)
from vantage6.server.resource._schema import (
    CollaborationSchema,
    TaskSchema,
    OrganizationSchema,
    NodeSchemaSimple
)
from vantage6.server.resource import (
    with_user_or_node,
    with_user,
    only_for,
    ServicesResources
)


module_name = __name__.split('.')[-1]
log = logging.getLogger(module_name)


def setup(api, api_base, services):
    path = "/".join([api_base, module_name])
    log.info(f'Setting up "{path}" and subdirectories')

    api.add_resource(
        Collaboration,
        path,
        endpoint='collaboration_without_id',
        methods=('GET', 'POST'),
        resource_class_kwargs=services
    )
    api.add_resource(
        Collaboration,
        path + '/<int:id>',
        endpoint='collaboration_with_id',
        methods=('GET', 'PATCH', 'DELETE'),
        resource_class_kwargs=services
    )
    api.add_resource(
        CollaborationOrganization,
        path+'/<int:id>/organization',
        endpoint='collaboration_with_id_organization',
        methods=('GET', 'POST', 'DELETE'),
        resource_class_kwargs=services
    )
    api.add_resource(
        CollaborationNode,
        path+'/<int:id>/node',
        endpoint='collaboration_with_id_node',
        methods=('GET', 'POST', 'DELETE'),
        resource_class_kwargs=services
    )
    api.add_resource(
        CollaborationTask,
        path+'/<int:id>/task',
        endpoint='collaboration_with_id_task',
        methods=('GET', 'POST', 'DELETE'),
        resource_class_kwargs=services
    )


# Schemas
collaboration_schema = CollaborationSchema()
tasks_schema = TaskSchema()
org_schema = OrganizationSchema()


# -----------------------------------------------------------------------------
# Permissions
# -----------------------------------------------------------------------------
def permissions(permissions: PermissionManager):
    add = permissions.appender(module_name)

    add(scope=S.GLOBAL, operation=P.VIEW,
        description="view any collaboration")
    add(scope=S.ORGANIZATION, operation=P.VIEW, assign_to_container=True,
        assign_to_node=True,
        description="view collaborations of your organization")

    add(scope=S.GLOBAL, operation=P.EDIT,
        description="edit any collaboration")
    # add(scope=S.ORGANIZATION, operation=P.EDIT,
    #     description="edit collaboration in which your organization "
    #     "participates")

    add(scope=S.GLOBAL, operation=P.CREATE,
        description="create a new collaboration")

    add(scope=S.GLOBAL, operation=P.DELETE,
        description="delete a collaboration")


# ------------------------------------------------------------------------------
# Resources / API's
# ------------------------------------------------------------------------------
class Collaboration(ServicesResources):

    def __init__(self, socketio, mail, api, permissions):
        super().__init__(socketio, mail, api, permissions)
        self.r = getattr(self.permissions, module_name)

    @with_user
    @swag_from(str(Path(r"swagger/post_collaboration_without_id.yaml")),
               endpoint='collaboration_without_id')
    def post(self):
        """create a new collaboration"""

        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, required=True,
                            help="This field cannot be left blank!")
        parser.add_argument('organization_ids', type=int, required=True,
                            action='append')
        parser.add_argument('encrypted', type=int, required=False)
        data = parser.parse_args()

        name = data["name"]
        if db.Collaboration.name_exists(name):
            return {"msg": f"Collaboration name '{name}' already exists!"}, \
                HTTPStatus.BAD_REQUEST

        if not self.r.c_glo.can():
            return {'msg': 'You lack the permission to do that!'}, \
                HTTPStatus.UNAUTHORIZED

        encrypted = True if data["encrypted"] == 1 else False

        collaboration = db.Collaboration(
            name=name,
            organizations=[
                db.Organization.get(org_id)
                for org_id in data['organization_ids']
                if db.Organization.get(org_id)
            ],
            encrypted=encrypted
        )

        collaboration.save()
        return collaboration_schema.dump(collaboration).data, HTTPStatus.OK

    @only_for(['user', 'node', 'container'])
    @swag_from(str(Path(r"swagger/get_collaboration_with_id.yaml")),
               endpoint='collaboration_with_id')
    @swag_from(str(Path(r"swagger/get_collaboration_without_id.yaml")),
               endpoint='collaboration_without_id')
    def get(self, id=None):
        """collaboration or list of collaborations in case no id is provided"""
        collaboration = db.Collaboration.get(id)

        # check that collaboration exists
        if not collaboration:
            return {"msg": "collaboration having id={} not found".format(id)},\
                HTTPStatus.NOT_FOUND

        if g.user:
            auth_org_id = g.user.organization.id
        elif g.node:
            auth_org_id = g.node.organization.id
        else:  # g.container
            auth_org_id = g.container["organization_id"]

        # verify permissions
        ids = [org.id for org in collaboration.organizations]
        if not self.r.v_glo.can():
            if not (self.r.v_org.can() and auth_org_id in ids):
                return {'msg': 'You lack the permission to do that!'}, \
                    HTTPStatus.UNAUTHORIZED

        return collaboration_schema.dump(collaboration, many=not id).data, \
            HTTPStatus.OK  # 200

    @with_user
    @swag_from(str(Path(r"swagger/patch_collaboration_with_id.yaml")),
               endpoint='collaboration_with_id')
    def patch(self, id):
        """update a collaboration"""

        collaboration = db.Collaboration.get(id)

        # check if collaboration exists
        if not collaboration:
            return {"msg": f"collaboration having collaboration_id={id} "
                    "can not be found"}, HTTPStatus.NOT_FOUND  # 404

        # verify permissions
        if not self.r.e_glo.can():
            return {'msg': 'You lack the permission to do that!'}, \
                HTTPStatus.UNAUTHORIZED

        # only update fields that are provided
        data = request.get_json()
        if "name" in data:
            collaboration.name = data["name"]
        if "organization_ids" in data:
            collaboration.organizations = [
                db.Organization.get(org_id)
                for org_id in data['organization_ids']
                if db.Organization.get(org_id)
            ]
        collaboration.save()

        return collaboration_schema.dump(collaboration, many=False).data, \
            HTTPStatus.OK  # 200

    @with_user
    @swag_from(str(Path(r"swagger/delete_collaboration_with_id.yaml")),
               endpoint='collaboration_with_id')
    def delete(self, id):
        """delete collaboration"""

        collaboration = db.Collaboration.get(id)
        if not collaboration:
            return {"msg": "collaboration id={} is not found".format(id)}, \
                HTTPStatus.NOT_FOUND

        # verify permissions
        if not self.r.d_glo.can():
            return {'msg': 'You lack the permission to do that!'}, \
                HTTPStatus.UNAUTHORIZED

        collaboration.delete()
        return {"msg": "node id={} successfully deleted".format(id)}, \
            HTTPStatus.OK


class CollaborationOrganization(ServicesResources):
    """Resource for /api/collaboration/<int:id>/organization."""

    @only_for(["node", "user", "container"])
    @swag_from(str(Path(r"swagger/get_collaboration_organization.yaml")),
               endpoint='collaboration_with_id_organization')
    def get(self, id):
        """Return organizations for a specific collaboration."""
        collaboration = db.Collaboration.get(id)
        if not collaboration:
            return {"msg": f"collaboration having collaboration_id={id} can "
                    "not be found"}, HTTPStatus.NOT_FOUND

        # only users that belong to the collaboration can view collaborators
        # organization_ids = collaboration.get_organization_ids()
        org_schema = OrganizationSchema()
        return org_schema.dump(collaboration.organizations, many=True).data, \
            HTTPStatus.OK

    @with_user
    @swag_from(str(Path(r"swagger/post_collaboration_organization.yaml")),
               endpoint='collaboration_with_id_organization')
    def post(self, id):
        """Add an organizations to a specific collaboration."""
        # get collaboration to which te organization should be added
        collaboration = db.Collaboration.get(id)
        if not collaboration:
            return {"msg": f"collaboration having collaboration_id={id} can "
                    "not be found"}, HTTPStatus.NOT_FOUND

        # get the organization
        data = request.get_json()
        organization = db.Organization.get(data['id'])
        if not organization:
            return {"msg": "organization with id={} is not found"}, \
                HTTPStatus.NOT_FOUND

        # append organization to the collaboration
        collaboration.organizations.append(organization)
        collaboration.save()
        return collaboration.organizations

    @with_user
    @swag_from(str(Path(r"swagger/delete_collaboration_organization.yaml")),
               endpoint='collaboration_with_id_organization')
    def delete(self, id):
        """Removes an organization from a collaboration."""
        # get collaboration from which organization should be removed
        collaboration = db.Collaboration.get(id)
        if not collaboration:
            return {"msg": f"collaboration having collaboration_id={id} can "
                    "not be found"}, HTTPStatus.NOT_FOUND

        # get organization which should be deleted
        data = request.get_json()
        organization = db.Organization.get(data['id'])
        if not organization:
            return {"msg": "organization with id={} is not found"}, \
                HTTPStatus.NOT_FOUND

        # delete organization and update
        collaboration.organizations.remove(organization)
        collaboration.save()
        return {"msg": f"organization id={data['id']} successfully deleted "
                f"from collaboration id={id}"}, HTTPStatus.OK


class CollaborationNode(ServicesResources):
    """Resource for /api/collaboration/<int:id>/node."""

    node_schema = NodeSchemaSimple()

    @with_user
    @swag_from(str(Path(r"swagger/get_collaboration_node.yaml")),
               endpoint='collaboration_with_id_node')
    def get(self, id):
        """"Return a list of nodes that belong to the collaboration."""
        collaboration = db.Collaboration.get(id)
        if not collaboration:
            return {"msg": f"collaboration having collaboration_id={id} can "
                    "not be found"}, HTTPStatus.NOT_FOUND

        return self.node_schema.dump(collaboration.nodes, many=True).data, \
            HTTPStatus.OK

    @with_user
    @swag_from(str(Path(r"swagger/post_collaboration_node.yaml")),
               endpoint='collaboration_with_id_node')
    def post(self, id):
        """Add an node to a specific collaboration."""
        collaboration = db.Collaboration.get(id)
        if not collaboration:
            return {"msg": "collaboration having collaboration_id={id} can "
                    "not be found"}, HTTPStatus.NOT_FOUND

        data = request.get_json()
        node = db.Node.get(data['id'])
        if not node:
            return {"msg": "node id={} not found"}, HTTPStatus.NOT_FOUND
        if node in collaboration.nodes:
            return {"msg": "node id={data['id']} is already in collaboration "
                    f"id={id}"}, HTTPStatus.BAD_REQUEST

        collaboration.nodes.append(node)
        collaboration.save()
        return self.node_schema.dump(collaboration.nodes, many=True),\
            HTTPStatus.CREATED

    @with_user
    @swag_from(str(Path(r"swagger/delete_collaboration_node.yaml")),
               endpoint='collaboration_with_id_node')
    def delete(self, id):
        """Remove node from collaboration."""
        collaboration = db.Collaboration.get(id)
        if not collaboration:
            return {"msg": f"collaboration having collaboration_id={id} can "
                    "not be found"}, HTTPStatus.NOT_FOUND

        data = request.get_json()
        node = db.Node.get(data['id'])
        if not node:
            return {"msg": "node id={} not found"}, HTTPStatus.NOT_FOUND
        if node not in collaboration.nodes:
            return {"msg": f"node id={data['id']} is not part of "
                    "collaboration id={id}"}, HTTPStatus.BAD_REQUEST

        collaboration.nodes.remove(node)
        return {"msg": "node id={data['id']} removed from collaboration "
                "id={id}"}, HTTPStatus.OK


class CollaborationTask(ServicesResources):
    """Resource for /api/collaboration/<int:id>/task."""

    @with_user_or_node
    @swag_from(str(Path(r"swagger/get_collaboration_task.yaml")),
               endpoint='collaboration_with_id_task')
    def get(self, id):
        """List of tasks that belong to a collaboration"""
        collaboration = db.Collaboration.get(id)
        return tasks_schema.dump(collaboration.tasks, many=True)

    @with_user
    @swag_from(str(Path(r"swagger/post_collaboration_task.yaml")),
               endpoint='collaboration_with_id_task')
    def post(self, id):
        """Attach new task to collaboration"""
        collaboration = db.Collaboration.get(id)
        if not collaboration:
            return {"msg": f"collaboration having collaboration_id={id} can "
                    "not be found"}, HTTPStatus.NOT_FOUND

        data = request.get_json()

        input_ = data.get('input', '') if \
            isinstance(data.get('input', ''), str) else \
            json.dumps(data.get('input'))

        task = db.Task(
            collaboration=collaboration,
            name=data.get('name', ''),
            description=data.get('description', ''),
            image=data.get('image', ''),
            input=input_,
        )
        task.save()

        for organization in collaboration.organizations:
            result = db.Result(
                task=task,
                organization=organization
            )
            result.save()

        return tasks_schema.dump(collaboration.tasks, many=True)

    @with_user
    @swag_from(str(Path(r"swagger/delete_collaboration_task.yaml")),
               endpoint='collaboration_with_id_task')
    def delete(self, id):
        """Remove task from collaboration"""
        collaboration = db.Collaboration.get(id)
        if not collaboration:
            return {"msg": f"collaboration having collaboration_id={id} can "
                    "not be found"}, HTTPStatus.NOT_FOUND

        data = request.get_json()
        task_id = data['task_id']
        task = db.Task.get(task_id)
        if not task:
            return {"msg": f"Task id={task_id} not found"}, \
                HTTPStatus.NOT_FOUND
        if task_id not in collaboration.get_task_ids():
            return {"msg": f"Task id={task_id} is not part of collaboration "
                    "id={id}"}, HTTPStatus.BAD_REQUEST
        task.delete()
        return {"msg": "Task id={task_id} is removed from collaboration "
                f"id={id}"}, HTTPStatus.OK
