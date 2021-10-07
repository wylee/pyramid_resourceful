"""SQLAlchemy ORM Example

To run this example, first run ``poetry install``, which will install
the necessary development dependencies. Then run the following command
from the top level ``pyramid_resourceful`` directory::

    ./examples/run-example sqlalchemy

Which is equivalent to::

    PYTHONPATH=. pserve -n sqlalchemy --reload examples/example.ini

Then open http://localhost:6544/ in your browser. From there, you can
play around with CRUD from a very simple UI.

A temporary SQLite database named ``example.db`` will be created in the
``examples`` directory the first time this example is run. On subsequent
runs, if this database already exists, all of its tables will be dropped
and recreated.

"""
from pyramid.config import Configurator
from pyramid.csrf import CookieCSRFStoragePolicy

from pyramid_resourceful.sqlalchemy import (
    SQLAlchemyContainerResource,
    SQLAlchemyItemResource,
)

from sqlalchemy import insert
from sqlalchemy.engine import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import Column
from sqlalchemy.types import Integer, String

import zope.sqlalchemy


Base = declarative_base()


class Item(Base):

    __tablename__ = "item"

    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    description = Column(String)

    def __json__(self, _request):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
        }

    def __str__(self):
        return f"Item(id={self.id}, title={self.title}, description={self.description})"



def main(global_config, **settings):
    def get_request_session(request):
        """Get managed session for current request."""
        session = session_factory()
        zope.sqlalchemy.register(session, transaction_manager=request.tm)
        return session

    engine = create_engine(f"sqlite:///{settings['db.path']}", future=True)
    session_factory = sessionmaker(bind=engine, future=True)
    create_and_populate_database(engine)

    config = Configurator(settings=settings)

    with config:
        config.include("pyramid_mako")
        config.include("pyramid_resourceful")
        config.include("pyramid_tm")

        config.set_csrf_storage_policy(CookieCSRFStoragePolicy())
        config.set_default_csrf_options(require_csrf=True)

        config.add_request_method(get_request_session, "dbsession", reify=True)

        # These are the pyramid_resourceful bits
        resource_args = {"model": Item}
        config.add_resource(
            SQLAlchemyContainerResource,
            resource_args=resource_args,
            name="root",
            path="/",
            renderers=["example.mako"],
        )
        with config.add_resources(
            path_prefix="/items/",
            resource_args=resource_args,
        ) as add_resource:
            add_resource(
                SQLAlchemyContainerResource,
                resource_args=resource_args,
                name="items",
                path="",
                renderers=["json", "example.mako"],
            )
            add_resource(
                SQLAlchemyItemResource,
                resource_args=resource_args,
                name="item",
                path=r"{id:\d+}",
            )
        config.enable_post_tunneling()

    return config.make_wsgi_app()


def create_and_populate_database(engine):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    statement = insert(Item.__table__).values(
        (
            {"title": "One", "description": "First"},
            {"title": "Two", "description": "Second"},
            {"title": "Three", "description": "Third"},
        )
    )
    with engine.connect() as cxn:
        cxn.execute(statement)
        cxn.commit()
