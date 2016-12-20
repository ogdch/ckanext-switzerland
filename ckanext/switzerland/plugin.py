# coding=UTF-8

from ckanext.switzerland import validators as v
from ckanext.switzerland.logic import (
    ogdch_dataset_count, ogdch_dataset_terms_of_use,
    ogdch_dataset_by_identifier, ogdch_content_headers
)
from ckanext.switzerland.helpers import (
    get_dataset_count, get_group_count, get_app_count,
    get_org_count, get_tweet_count, get_localized_value,
    get_localized_org, localize_json_title, get_langs,
    get_frequency_name, get_terms_of_use_icon, get_dataset_terms_of_use,
    get_political_level, get_dataset_by_identifier, get_readable_file_size,
    simplify_terms_of_use, parse_json, get_piwik_config,
    ogdch_localised_number, ogdch_group_tree, map_to_valid_format
)

import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from ckan import logic
import ckan.lib.helpers as h
from ckan.lib.munge import munge_title_to_name
import pylons
import json
import re
import collections
from webhelpers.html import HTML
from webhelpers import paginate
import urlparse
import os
import logging
log = logging.getLogger(__name__)


class OgdchPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IValidators)
    plugins.implements(plugins.IFacets)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.ITemplateHelpers)

    # IConfigurer

    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'public')
        toolkit.add_resource('fanstatic', 'switzerland')

    # IValidators

    def get_validators(self):
        return {
            'multiple_text': v.multiple_text,
            'multiple_text_output': v.multiple_text_output,
            'multilingual_text_output': v.multilingual_text_output,
            'list_of_dicts': v.list_of_dicts,
            'timestamp_to_datetime': v.timestamp_to_datetime,
            'ogdch_multiple_choice': v.ogdch_multiple_choice,
            'ogdch_unique_identifier': v.ogdch_unique_identifier,
            'temporals_to_datetime_output': v.temporals_to_datetime_output,
            'parse_json': parse_json,
        }

    # IFacets

    def dataset_facets(self, facets_dict, package_type):
        lang_code = pylons.request.environ['CKAN_LANG']
        facets_dict = collections.OrderedDict()
        facets_dict['groups'] = plugins.toolkit._('Categories')
        facets_dict['keywords_' + lang_code] = plugins.toolkit._('Keywords')
        facets_dict['organization'] = plugins.toolkit._('Organizations')
        facets_dict['political_level'] = plugins.toolkit._('Political levels')
        facets_dict['res_rights'] = plugins.toolkit._('Terms of use')
        facets_dict['res_format'] = plugins.toolkit._('Formats')
        return facets_dict

    def group_facets(self, facets_dict, group_type, package_type):
        lang_code = pylons.request.environ['CKAN_LANG']
        # the IFacets implementation of CKAN 2.4 is broken,
        # clear the dict instead and change the passed in argument
        facets_dict.clear()
        facets_dict['keywords_' + lang_code] = plugins.toolkit._('Keywords')
        facets_dict['organization'] = plugins.toolkit._('Organizations')
        facets_dict['political_level'] = plugins.toolkit._('Political levels')
        facets_dict['res_rights'] = plugins.toolkit._('Terms of use')
        facets_dict['res_format'] = plugins.toolkit._('Formats')

    def organization_facets(self, facets_dict, organization_type,
                            package_type):
        lang_code = pylons.request.environ['CKAN_LANG']
        # the IFacets implementation of CKAN 2.4 is broken,
        # clear the dict instead and change the passed in argument
        facets_dict.clear()
        facets_dict['groups'] = plugins.toolkit._('Categories')
        facets_dict['keywords_' + lang_code] = plugins.toolkit._('Keywords')
        facets_dict['res_rights'] = plugins.toolkit._('Terms of use')
        facets_dict['res_format'] = plugins.toolkit._('Formats')

    # IActions

    def get_actions(self):
        """
        Expose new API methods
        """
        return {
            'ogdch_dataset_count': ogdch_dataset_count,
            'ogdch_dataset_terms_of_use': ogdch_dataset_terms_of_use,
            'ogdch_dataset_by_identifier': ogdch_dataset_by_identifier,
            'ogdch_content_headers': ogdch_content_headers,
        }

    # ITemplateHelpers

    def get_helpers(self):
        """
        Provide template helper functions
        """
        return {
            'get_dataset_count': get_dataset_count,
            'get_group_count': get_group_count,
            'get_app_count': get_app_count,
            'get_org_count': get_org_count,
            'get_tweet_count': get_tweet_count,
            'get_localized_org': get_localized_org,
            'localize_json_title': localize_json_title,
            'get_frequency_name': get_frequency_name,
            'get_political_level': get_political_level,
            'get_terms_of_use_icon': get_terms_of_use_icon,
            'get_dataset_terms_of_use': get_dataset_terms_of_use,
            'get_dataset_by_identifier': get_dataset_by_identifier,
            'get_readable_file_size': get_readable_file_size,
            'get_piwik_config': get_piwik_config,
            'ogdch_localised_number': ogdch_localised_number,
            'ogdch_group_tree': ogdch_group_tree,
        }


class OgdchLanguagePlugin(plugins.SingletonPlugin):
    """
    Handles language dictionaries in data_dict (pkg_dict).
    """

    def before_view(self, pkg_dict):
        pkg_dict = self._prepare_package_json(pkg_dict)

        return pkg_dict

    def _ignore_field(self, key):
        return False

    def _prepare_package_json(self, pkg_dict):
        # parse all json strings in dict
        pkg_dict = self._package_parse_json_strings(pkg_dict)

        # map ckan fields
        pkg_dict = self._package_map_ckan_default_fields(pkg_dict)

        # prepare format of resources
        pkg_dict = self._prepare_resources_format(pkg_dict)

        try:
            # Do not change the resulting dict for API requests
            path = pylons.request.path
            if path.startswith('/api'):
                return pkg_dict
        except TypeError:
            # we get here if there is no request (i.e. on the command line)
            return pkg_dict

        # replace langauge dicts with requested language strings
        desired_lang_code = self._get_request_language()
        pkg_dict = self._package_reduce_to_requested_language(
            pkg_dict, desired_lang_code
        )

        return pkg_dict

    def _get_request_language(self):
        try:
            return pylons.request.environ['CKAN_LANG']
        except TypeError:
            return pylons.config.get('ckan.locale_default', 'en')

    def _package_parse_json_strings(self, pkg_dict):
        # try to parse all values as JSON
        for key, value in pkg_dict.iteritems():
            pkg_dict[key] = parse_json(value)

        # groups
        if 'groups' in pkg_dict and pkg_dict['groups'] is not None:
            for group in pkg_dict['groups']:
                """
                TODO: somehow the title is messed up here,
                but the display_name is okay
                """
                group['title'] = group['display_name']
                for field in group:
                    group[field] = parse_json(group[field])

        # organization
        if 'organization' in pkg_dict and pkg_dict['organization'] is not None:
            for field in pkg_dict['organization']:
                pkg_dict['organization'][field] = parse_json(
                    pkg_dict['organization'][field]
                )

        return pkg_dict

    def _package_map_ckan_default_fields(self, pkg_dict):  # noqa
        pkg_dict['display_name'] = pkg_dict['title']

        if pkg_dict.get('maintainer') is None:
            try:
                pkg_dict['maintainer'] = pkg_dict['contact_points'][0]['name']  # noqa
            except (KeyError, IndexError):
                pass

        if pkg_dict.get('maintainer_email') is None:
            try:
                pkg_dict['maintainer_email'] = pkg_dict['contact_points'][0]['email']  # noqa
            except (KeyError, IndexError):
                pass

        if pkg_dict.get('author') is None:
            try:
                pkg_dict['author'] = pkg_dict['publishers'][0]['label']  # noqa
            except (KeyError, IndexError):
                pass

        if pkg_dict.get('resources') is not None:
            for resource in pkg_dict['resources']:
                resource['name'] = resource['title']

        return pkg_dict

    def _prepare_resources_format(self, pkg_dict):
        if pkg_dict.get('resources') is not None:
            for resource in pkg_dict['resources']:
                resource = self._prepare_resource_format(resource)

                # if format could not be mapped and media_type exists use this value  # noqa
                if (resource.get('format') is None and
                        resource.get('media_type')):
                    resource['format'] = resource['media_type'].split('/')[-1]

        return pkg_dict

    # Generates format of resource and saves it in format field
    def _prepare_resource_format(self, resource):
        resource_format = ''

        # get format from download_url file extension if available
        if resource.get('download_url') is not None:
            path = urlparse.urlparse(resource['download_url']).path
            ext = os.path.splitext(path)[1]
            if ext:
                resource_format = ext.replace('.', '').lower()

        # get format from media_type field if available
        if not resource_format and resource.get('media_type') is not None:  # noqa
            resource_format = resource['media_type'].split('/')[-1].lower()

        # get format from format field if available (lol)
        if not resource_format and resource.get('format') is not None:
            resource_format = resource['format'].split('/')[-1].lower()

        mapped_format = map_to_valid_format(resource_format)
        if mapped_format:
            # if format could be successfully mapped write it to format field
            resource['format'] = mapped_format
        else:
            # else return None (these will be indexed as N/A)
            resource['format'] = None

        return resource

    def _extract_lang_value(self, value, lang_code):
        new_value = parse_json(value)

        if isinstance(new_value, dict):
            return get_localized_value(new_value, lang_code, default_value='')
        return value

    def _package_reduce_to_requested_language(self, pkg_dict, desired_lang_code):  # noqa
        # pkg fields
        for key, value in pkg_dict.iteritems():
            if not self._ignore_field(key):
                pkg_dict[key] = self._extract_lang_value(
                    value,
                    desired_lang_code
                )

        # groups
        pkg_dict = self._reduce_group_language(pkg_dict, desired_lang_code)

        # organization
        pkg_dict = self._reduce_org_language(pkg_dict, desired_lang_code)

        # resources
        pkg_dict = self._reduce_res_language(pkg_dict, desired_lang_code)

        return pkg_dict

    def _reduce_group_language(self, pkg_dict, desired_lang_code):
        if 'groups' in pkg_dict and pkg_dict['groups'] is not None:
            try:
                for element in pkg_dict['groups']:
                    for field in element:
                        element[field] = self._extract_lang_value(
                            element[field],
                            desired_lang_code
                        )
            except TypeError:
                pass

        return pkg_dict

    def _reduce_org_language(self, pkg_dict, desired_lang_code):
        if 'organization' in pkg_dict and pkg_dict['organization'] is not None:
            try:
                for field in pkg_dict['organization']:
                    pkg_dict['organization'][field] = self._extract_lang_value(
                        pkg_dict['organization'][field],
                        desired_lang_code
                    )
            except TypeError:
                pass
        return pkg_dict

    def _reduce_res_language(self, pkg_dict, desired_lang_code):
        if 'resources' in pkg_dict and pkg_dict['resources'] is not None:
            try:
                for element in pkg_dict['resources']:
                    for field in element:
                        element[field] = self._extract_lang_value(
                            element[field],
                            desired_lang_code
                        )
            except TypeError:
                pass
        return pkg_dict


class OgdchGroupPlugin(OgdchLanguagePlugin):
    plugins.implements(plugins.IGroupController, inherit=True)

    # IGroupController
    def before_view(self, pkg_dict):
        return super(OgdchGroupPlugin, self).before_view(pkg_dict)


class OgdchOrganizationPlugin(OgdchLanguagePlugin):
    plugins.implements(plugins.IOrganizationController, inherit=True)

    # IOrganizationController
    def before_view(self, pkg_dict):
        return super(OgdchOrganizationPlugin, self).before_view(pkg_dict)


class OgdchResourcePlugin(OgdchLanguagePlugin):
    plugins.implements(plugins.IResourceController, inherit=True)

    # IResourceController
    def before_show(self, res_dict):
        res_dict = super(OgdchResourcePlugin, self).before_view(res_dict)
        res_dict = self._prepare_resource_format(res_dict)

        # if format could not be mapped and media_type exists use this value
        if res_dict.get('format') is None and res_dict.get('media_type'):
            res_dict['format'] = res_dict['media_type'].split('/')[-1]

        return res_dict

    def _ignore_field(self, key):
        return key == 'tracking_summary'


class OgdchPackagePlugin(OgdchLanguagePlugin):
    plugins.implements(plugins.IPackageController, inherit=True)

    def is_supported_package_type(self, pkg_dict):
        # only package type 'dataset' is supported (not harvesters!)
        try:
            return (pkg_dict['type'] == 'dataset')
        except KeyError:
            return False

    # IPackageController
    def before_view(self, pkg_dict):
        if not self.is_supported_package_type(pkg_dict):
            return pkg_dict

        return super(OgdchPackagePlugin, self).before_view(pkg_dict)

#     TODO: before_view isn't called in API requests -> after_show is
#           BUT (!) after_show is also called when packages get indexed
#           and there we need all languages.
#           -> find a solution to _prepare_package_json() in an API call.
#     def after_show(self, context, pkg_dict):
#         if not self.is_supported_package_type(pkg_dict):
#             return pkg_dict
#
#         return super(OgdchPackagePlugin, self).before_view(pkg_dict)

    def after_show(self, context, pkg_dict):
        if not self.is_supported_package_type(pkg_dict):
            return pkg_dict

        pkg_dict = self._package_map_ckan_default_fields(pkg_dict)

        # groups
        if pkg_dict['groups'] is not None:
            for group in pkg_dict['groups']:
                """
                TODO: somehow the title is messed up here,
                but the display_name is okay
                """
                group['title'] = group['display_name']
                for field in group:
                    group[field] = parse_json(group[field])

        # load organization from API to get all fields defined in schema
        # by default, CKAN loads organizations only from the database
        if pkg_dict['owner_org'] is not None:
            pkg_dict['organization'] = logic.get_action('organization_show')(
                {},
                {
                    'id': pkg_dict['owner_org'],
                    'include_users': False,
                    'include_followers': False,
                }
            )

        return pkg_dict

    def before_index(self, search_data):
        if not self.is_supported_package_type(search_data):
            return search_data

        extract_title = LangToString('title')
        validated_dict = json.loads(search_data['validated_data_dict'])

        # log.debug(pprint.pformat(validated_dict))

        search_data['res_name'] = [extract_title(r) for r in validated_dict[u'resources']]  # noqa
        search_data['res_description'] = [LangToString('description')(r) for r in validated_dict[u'resources']]  # noqa
        search_data['res_format'] = self._prepare_formats_for_index(validated_dict[u'resources'])  # noqa
        search_data['res_rights'] = [simplify_terms_of_use(r['rights']) for r in validated_dict[u'resources']]  # noqa
        search_data['title_string'] = extract_title(validated_dict)
        search_data['description'] = LangToString('description')(validated_dict)  # noqa
        if 'political_level' in validated_dict[u'organization']:
            search_data['political_level'] = validated_dict[u'organization'][u'political_level']  # noqa

        try:
            # index language-specific values (or it's fallback)
            text_field_items = {}
            for lang_code in get_langs():
                search_data['title_' + lang_code] = get_localized_value(
                    validated_dict['title'],
                    lang_code
                )
                search_data['title_string_' + lang_code] = munge_title_to_name(
                    get_localized_value(validated_dict['title'], lang_code)
                )
                search_data['description_' + lang_code] = get_localized_value(
                    validated_dict['description'],
                    lang_code
                )
                search_data['keywords_' + lang_code] = get_localized_value(
                    validated_dict['keywords'],
                    lang_code
                )

                text_field_items['text_' + lang_code] = [get_localized_value(validated_dict['description'], lang_code)]  # noqa
                text_field_items['text_' + lang_code].extend(search_data['keywords_' + lang_code])  # noqa
                text_field_items['text_' + lang_code].extend([r['title'][lang_code] for r in validated_dict['resources'] if r['title'][lang_code]])  # noqa
                text_field_items['text_' + lang_code].extend([r['description'][lang_code] for r in validated_dict['resources'] if r['description'][lang_code]])  # noqa

            # flatten values for text_* fields
            for key, value in text_field_items.iteritems():
                search_data[key] = ' '.join(value)

        except KeyError:
            pass

        # log.debug(pprint.pformat(search_data))
        return search_data

    # generates a set with formats of all resources
    def _prepare_formats_for_index(self, resources):
        formats = set()
        for r in resources:
            resource = self._prepare_resource_format(r)
            if resource['format']:
                formats.add(resource['format'])
            else:
                formats.add('N/A')

        return formats

    # borrowed from ckanext-multilingual (core extension)
    def before_search(self, search_params):
        """
        Adjust search parameters
        """

        '''
        search in correct language-specific field and boost
        results in current language
        '''
        lang_set = get_langs()
        try:
            current_lang = pylons.request.environ['CKAN_LANG']
        except TypeError as err:
            if err.message == ('No object (name: request) has been registered '
                               'for this thread'):
                # This happens when this code gets called as part of a paster
                # command rather then as part of an HTTP request.
                current_lang = pylons.config.get('ckan.locale_default')
            else:
                raise

        # fallback to default locale if locale not in suported langs
        if current_lang not in lang_set:
            current_lang = pylons.config.get('ckan.locale_default', 'en')
        # treat current lang differenly so remove from set
        lang_set.remove(current_lang)

        # weight current lang more highly
        query_fields = 'title_%s^8 text_%s^4' % (current_lang, current_lang)

        for lang in lang_set:
            query_fields += ' title_%s^2 text_%s' % (lang, lang)

        search_params['qf'] = query_fields

        '''
        Unless the query is already being filtered by any type
        (either positively, or negatively), reduce to only display
        'dataset' type
        This is done because by standard all types are displayed, this
        leads to strange situations where e.g. harvest sources are shown
        on organization pages.
        TODO: fix issue https://github.com/ckan/ckan/issues/2803 in CKAN core
        '''
        fq = search_params.get('fq', '')
        if 'dataset_type:' not in fq:
            search_params.update({'fq': "%s +dataset_type:dataset" % fq})

        return search_params


class OgdchOrganisationSearchPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IRoutes, inherit=True)

    # IRouter
    # Redirect organization_read /organization/{id} to custom controller
    # fix the search on the org page and use Hierarchy if needed

    def before_map(self, map):
        map.connect('organization_read', '/organization/{id}',
                    controller='ckanext.switzerland.controller:OgdchOrganizationSearchController',  # noqa
                    action='read')
        return map


class LangToString(object):
    def __init__(self, attribute):
        self.attribute = attribute

    def __call__(self, data_dict):
        lang = data_dict[self.attribute]
        return (
            '%s - %s - %s - %s' % (
                lang.get('de', ''),
                lang.get('fr', ''),
                lang.get('it', ''),
                lang.get('en', '')
            )
        )


# Monkeypatch to style CKAN pagination
class OGDPage(paginate.Page):
    # Curry the pager method of the webhelpers.paginate.Page class, so we have
    # our custom layout set as default.

    def pager(self, *args, **kwargs):
        kwargs.update(
            format=u"<ul class='pagination'>$link_previous ~2~ $link_next</ul>",  # noqa
            symbol_previous=u'«', symbol_next=u'»',
            curpage_attr={'class': 'active'}, link_attr={}
        )
        return super(OGDPage, self).pager(*args, **kwargs)

    # Put each page link into a <li> (for Bootstrap to style it)

    def _pagerlink(self, page, text, extra_attributes=None):
        anchor = super(OGDPage, self)._pagerlink(page, text)
        extra_attributes = extra_attributes or {}
        return HTML.li(anchor, **extra_attributes)

    # Change 'current page' link from <span> to <li><a>
    # and '..' into '<li><a>..'
    # (for Bootstrap to style them properly)

    def _range(self, regexp_match):
        html = super(OGDPage, self)._range(regexp_match)
        # Convert ..
        dotdot = '<span class="pager_dotdot">..</span>'
        dotdot_link = HTML.li(HTML.a('...', href='#'), class_='disabled')
        html = re.sub(dotdot, dotdot_link, html)

        # Convert current page
        text = '%s' % self.page
        current_page_span = str(HTML.span(c=text, **self.curpage_attr))
        current_page_link = self._pagerlink(self.page, text,
                                            extra_attributes=self.curpage_attr)
        return re.sub(current_page_span, current_page_link, html)

h.Page = OGDPage
