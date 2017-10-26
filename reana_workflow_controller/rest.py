# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017 CERN.
#
# REANA is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# REANA is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# REANA; if not, write to the Free Software Foundation, Inc., 59 Temple Place,
# Suite 330, Boston, MA 02111-1307, USA.
#
# In applying this license, CERN does not waive the privileges and immunities
# granted to it by virtue of its status as an Intergovernmental Organization or
# submit itself to any jurisdiction.

"""REANA Workflow Controller REST API."""

import traceback

import os
from flask import Blueprint, abort, jsonify, request
from werkzeug.utils import secure_filename

from .factory import db
from .models import User
from .tasks import run_yadage_workflow, run_cwl_workflow

organization_to_queue = {
    'alice': 'alice-queue',
    'atlas': 'atlas-queue',
    'lhcb': 'lhcb-queue',
    'cms': 'cms-queue',
    'default': 'default-queue'
}

restapi_blueprint = Blueprint('api', __name__)


@restapi_blueprint.before_request
def before_request():
    """Retrieve organization from request."""
    try:
        db.choose_organization(request.args['organization'])
    except KeyError as e:
        return jsonify({"message": "An organization should be provided"}), 400
    except ValueError as e:
        return jsonify({"message": str(e)}), 404
    except Exception as e:
        return jsonify({"message": str(e)}), 500


@restapi_blueprint.route('/workflows', methods=['GET'])
def get_workflows():  # noqa
    r"""Get all workflows.

    ---
    get:
      summary: Returns all workflows.
      description: >-
        This resource is expecting an organization name and an user UUID. The
        information related to all workflows for a given user will be served
        as JSON
      operationId: get_workflows
      produces:
        - application/json
      parameters:
        - name: organization
          in: query
          description: Required. Organization which the worklow belongs to.
          required: true
          type: string
        - name: user
          in: query
          description: Required. UUID of workflow owner.
          required: true
          type: string
      responses:
        200:
          description: >-
            Requests succeeded. The response contains the current workflows
            for a given user and organization.
          schema:
            type: array
            items:
              type: object
              properties:
                id:
                  type: string
                organization:
                  type: string
                status:
                  type: string
                user:
                  type: string
          examples:
            application/json:
              [
                {
                  "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                  "organization": "default_org",
                  "status": "running",
                  "user": "00000000-0000-0000-0000-000000000000"
                },
                {
                  "id": "3c9b117c-d40a-49e3-a6de-5f89fcada5a3",
                  "organization": "default_org",
                  "status": "finished",
                  "user": "00000000-0000-0000-0000-000000000000"
                },
                {
                  "id": "72e3ee4f-9cd3-4dc7-906c-24511d9f5ee3",
                  "organization": "default_org",
                  "status": "waiting",
                  "user": "00000000-0000-0000-0000-000000000000"
                },
                {
                  "id": "c4c0a1a6-beef-46c7-be04-bf4b3beca5a1",
                  "organization": "default_org",
                  "status": "waiting",
                  "user": "00000000-0000-0000-0000-000000000000"
                }
              ]
        400:
          description: >-
            Request failed. The incoming data specification seems malformed.
        404:
          description: >-
            Request failed. User doesn't exist.
          examples:
            application/json:
              {
                "message": "User 00000000-0000-0000-0000-000000000000 doesn't
                            exist"
              }
        500:
          description: >-
            Request failed. Internal controller error.
          examples:
            application/json:
              {
                "message": "Either organization or user doesn't exist."
              }
    """
    try:
        organization = request.args['organization']
        user_uuid = request.args['user']
        user = User.query.filter(User.id_ == user_uuid).first()
        if not user:
            return jsonify(
                {'message': 'User {} does not exist'.format(user)}), 404

        workflows = []
        for workflow in user.workflows:
            workflows.append({'id': workflow.id_,
                              'status': workflow.status.name,
                              'organization': organization,
                              'user': user_uuid})

        return jsonify(workflows), 200
    except KeyError:
        return jsonify({"message": "Malformed request."}), 400
    except Exception as e:
        return jsonify({"message": str(e)}), 500


@restapi_blueprint.route('/workflows/<workflow_id>/workspace',
                         methods=['POST'])
def seed_workflow_workspace(workflow_id):
    r"""Seed workflow workspace.

    ---
    post:
      summary: Adds a file to the workflow workspace.
      description: >-
        This resource is expecting a workflow UUID and a file to place in the
        workflow workspace.
      operationId: seed_workflow
      consumes:
        - multipart/form-data
      produces:
        - application/json
      parameters:
        - name: organization
          in: query
          description: Required. Organization which the worklow belongs to.
          required: true
          type: string
        - name: user
          in: query
          description: Required. UUID of workflow owner.
          required: true
          type: string
        - name: workflow_id
          in: path
          description: Required. Workflow UUID.
          required: true
          type: string
        - name: file_content
          in: formData
          description: Required. File to add to the workflow workspace.
          required: true
          type: file
        - name: file_name
          in: query
          description: Required. File name.
          required: true
          type: string
      responses:
        200:
          description: >-
            Request succeeded. The file has been added to the workspace.
          schema:
            type: object
            properties:
              message:
                type: string
              workflow_id:
                type: string
          examples:
            application/json:
              {
                "message": "Workflow has been added to the workspace",
                "workflow_id": "cdcf48b1-c2f3-4693-8230-b066e088c6ac"
              }
        400:
          description: >-
            Request failed. The incoming data specification seems malformed
    """
    try:
        file_ = request.files['file_content'].stream.read()
        file_name = secure_filename(request.args['file_name'])
        return jsonify({'message': 'File successfully transferred'}), 200
    except KeyError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": str(e)}), 500


@restapi_blueprint.route('/yadage/remote', methods=['POST'])
def run_yadage_workflow_from_remote_endpoint():  # noqa
    r"""Create a new yadage workflow from a remote repository.

    ---
    post:
      summary: Creates a new yadage workflow from a remote repository.
      description: >-
        This resource is expecting JSON data with all the necessary information
        to instantiate a yadage workflow from a remote repository.
      operationId: run_yadage_workflow_from_remote
      consumes:
        - application/json
      produces:
        - application/json
      parameters:
        - name: organization
          in: query
          description: Required. Organization which the worklow belongs to.
          required: true
          type: string
        - name: user
          in: query
          description: Required. UUID of workflow owner.
          required: true
          type: string
        - name: workflow_data
          in: body
          description: >-
            Workflow information in JSON format with all the necessary data to
            instantiate a yadage workflow from a remote repository such as
            GitHub.
          required: true
          schema:
            type: object
            properties:
              toplevel:
                type: string
                description: >-
                  Yadage toplevel argument. It represents the remote repository
                  where the workflow should be pulled from.
              workflow:
                type: string
                description: >-
                  Yadage workflow parameter. It represents the name of the
                  workflow spec file name inside the remote repository.
              nparallel:
                type: integer
              preset_pars:
                type: object
                description: Workflow parameters.
      responses:
        200:
          description: >-
            Request succeeded. The workflow has been instantiated.
          schema:
            type: object
            properties:
              message:
                type: string
              workflow_id:
                type: string
          examples:
            application/json:
              {
                "message": "Workflow successfully launched",
                "workflow_id": "cdcf48b1-c2f3-4693-8230-b066e088c6ac"
              }
        400:
          description: >-
            Request failed. The incoming data specification seems malformed
    """
    try:
        if request.json:
            queue = organization_to_queue[request.args.get('organization')]
            resultobject = run_yadage_workflow.apply_async(
                args=[request.json],
                queue='yadage-{}'.format(queue)
            )
            return jsonify({'message': 'Workflow successfully launched',
                            'workflow_id': resultobject.id}), 200

    except (KeyError, ValueError):
        traceback.print_exc()
        abort(400)


@restapi_blueprint.route('/seed', methods=['POST'])
def seed():  # noqa
    try:
        if request.files:
            file = request.files['file']
            analysis_directory = os.path.join(
                os.getenv('SHARED_VOLUME', '/data'),
                '00000000-0000-0000-0000-000000000000',  # FIXME parameter from RWC
                'analyses')

            analysis_workspace = os.path.join(analysis_directory, 'workspace')

            if not os.path.exists(analysis_workspace):
                os.makedirs(analysis_workspace)
            file.save(analysis_workspace)
            return jsonify({'message': 'File saved'}), 200

    except (KeyError, ValueError):
        traceback.print_exc()
        abort(400)


@restapi_blueprint.route('/yadage/spec', methods=['POST'])
def run_yadage_workflow_from_spec_endpoint():  # noqa
    r"""Create a new yadage workflow.

    ---
    post:
      summary: Creates a new yadage workflow from a specification file.
      description: This resource is expecting a JSON yadage specification.
      operationId: run_yadage_workflow_from_spec
      consumes:
        - application/json
      produces:
        - application/json
      parameters:
        - name: organization
          in: query
          description: Required. Organization which the worklow belongs to.
          required: true
          type: string
        - name: user
          in: query
          description: Required. UUID of workflow owner.
          required: true
          type: string
        - name: workflow
          in: body
          description: >-
            JSON object including workflow parameters and workflow
            specification in JSON format (`yadageschemas.load()` output)
            with necessary data to instantiate a yadage workflow.
          required: true
          schema:
            type: object
            properties:
              parameters:
                type: object
                description: Workflow parameters.
              workflow_spec:
                type: object
                description: >-
                  Yadage specification in JSON format.
      responses:
        200:
          description: >-
            Request succeeded. The workflow has been instantiated.
          schema:
            type: object
            properties:
              message:
                type: string
              workflow_id:
                type: string
          examples:
            application/json:
              {
                "message": "Workflow successfully launched",
                "workflow_id": "cdcf48b1-c2f3-4693-8230-b066e088c6ac"
              }
        400:
          description: >-
            Request failed. The incoming data specification seems malformed
    """
    try:
        # hardcoded until confirmation from `yadage`
        nparallel = 10
        if request.json:
            arguments = {
                "nparallel": nparallel,
                "workflow": request.json['workflow_spec'],
                "toplevel": "",  # ignored when spec submited
                "preset_pars": request.json['parameters']
            }
            queue = organization_to_queue[request.args.get('organization')]
            resultobject = run_yadage_workflow.apply_async(
                args=[arguments],
                queue='yadage-{}'.format(queue)
            )
            return jsonify({'message': 'Workflow successfully launched',
                            'workflow_id': resultobject.id}), 200

    except (KeyError, ValueError):
        traceback.print_exc()
        abort(400)\
        
@restapi_blueprint.route('/cwl/remote', methods=['POST'])
def run_cwl_workflow_from_remote_endpoint():  # noqa
    r"""Create a new cwl workflow from a remote repository.

    ---
    post:
      summary: Creates a new cwl workflow from a remote repository.
      description: >-
        This resource is expecting JSON data with all the necessary information
        to instantiate a cwl workflow from a remote repository.
      operationId: run_cwl_workflow_from_remote
      consumes:
        - application/json
      produces:
        - application/json
      parameters:
        - name: organization
          in: query
          description: Required. Organization which the worklow belongs to.
          required: true
          type: string
        - name: user
          in: query
          description: Required. UUID of workflow owner.
          required: true
          type: string
        - name: workflow_data
          in: body
          description: >-
            Workflow information in JSON format with all the necessary data to
            instantiate a cwl workflow from a remote repository such as
            GitHub.
          required: true
          schema:
            type: object
            properties:
              toplevel:
                type: string
                description: >-
                  cwl toplevel argument. It represents the remote repository
                  where the workflow should be pulled from.
              workflow:
                type: string
                description: >-
                  cwl workflow parameter. It represents the name of the
                  workflow spec file name inside the remote repository.
              nparallel:
                type: integer
              preset_pars:
                type: object
                description: Workflow parameters.
      responses:
        200:
          description: >-
            Request succeeded. The workflow has been instantiated.
          schema:
            type: object
            properties:
              message:
                type: string
              workflow_id:
                type: string
          examples:
            application/json:
              {
                "message": "Workflow successfully launched",
                "workflow_id": "cdcf48b1-c2f3-4693-8230-b066e088c6ac"
              }
        400:
          description: >-
            Request failed. The incoming data specification seems malformed
    """
    try:
        if request.json:
            queue = organization_to_queue[request.args.get('organization')]
            resultobject = run_cwl_workflow.apply_async(
                args=[request.json],
                queue='cwl-{}'.format(queue)
            )
            return jsonify({'message': 'Workflow successfully launched',
                            'workflow_id': resultobject.id}), 200

    except (KeyError, ValueError):
        traceback.print_exc()
        abort(400)


@restapi_blueprint.route('/cwl/spec', methods=['POST'])
def run_cwl_workflow_from_spec_endpoint():  # noqa
    r"""Create a new cwl workflow.

    ---
    post:
      summary: Creates a new cwl workflow from a specification file.
      description: This resource is expecting a JSON cwl specification.
      operationId: run_cwl_workflow_from_spec
      consumes:
        - application/json
      produces:
        - application/json
      parameters:
        - name: organization
          in: query
          description: Required. Organization which the worklow belongs to.
          required: true
          type: string
        - name: user
          in: query
          description: Required. UUID of workflow owner.
          required: true
          type: string
        - name: workflow
          in: body
          description: >-
            JSON object including workflow parameters and workflow
            specification in JSON format (`cwlschemas.load()` output)
            with necessary data to instantiate a cwl workflow.
          required: true
          schema:
            type: object
            properties:
              parameters:
                type: object
                description: Workflow parameters.
              workflow_spec:
                type: object
                description: >-
                  cwl specification in JSON format.
      responses:
        200:
          description: >-
            Request succeeded. The workflow has been instantiated.
          schema:
            type: object
            properties:
              message:
                type: string
              workflow_id:
                type: string
          examples:
            application/json:
              {
                "message": "Workflow successfully launched",
                "workflow_id": "cdcf48b1-c2f3-4693-8230-b066e088c6ac"
              }
        400:
          description: >-
            Request failed. The incoming data specification seems malformed
    """
    try:
        if request.json:
            arguments = {
                "workflow": request.json['workflow_spec'],
                "inputs": request.json['parameters']
            }
            queue = organization_to_queue[request.args.get('organization')]
            resultobject = run_cwl_workflow.apply_async(
                args=[arguments],
                queue='cwl-{}'.format(queue)
            )
            return jsonify({'message': 'Workflow successfully launched',
                            'workflow_id': resultobject.id}), 200

    except (KeyError, ValueError):
        traceback.print_exc()
        abort(400)
