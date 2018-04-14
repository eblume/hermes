#!/usr/bin/env python3

"""Console script for hermes"""

import click


@click.group()
@click.option('--debug/--no-debug', default=False)
@click.pass_context
def cli(ctx, debug):
    ctx.obj['DEBUG'] = debug


@cli.command()
@click.pass_context
def sync(ctx):
    click.echo('Debug is %s' % (ctx.obj['DEBUG'] and 'on' or 'off'))


# setuptools entry point
def main():
    cli(obj={})


if __name__ == '__main__':
    main()
