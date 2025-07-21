import logging
from lark import Lark, Transformer, v_args       

from dataclasses import dataclass
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Updated ST Grammar with better declaration handling
ST_GRAMMAR = r"""
    ?start: program

    program: "PROGRAM" IDENTIFIER declaration_block* statement_block "END_PROGRAM"

    declaration_block: var_block | var_input_block | var_output_block

    var_block: "VAR" declaration+ "END_VAR" -> var_declarations
    var_input_block: "VAR_INPUT" declaration+ "END_VAR" -> var_input_declarations  
    var_output_block: "VAR_OUTPUT" declaration+ "END_VAR" -> var_output_declarations

    declaration: IDENTIFIER ":" type_name init_value? ";"

    init_value: ":=" literal

    type_name: "BOOL" -> bool_type
         | "INT" -> int_type  
         | "REAL" -> real_type
         | "TIME" -> time_type

    statement_block: statement+

    ?statement: assignment
              | if_statement
              | function_call ";"

    assignment: IDENTIFIER ":=" expression ";"

    if_statement: "IF" expression "THEN" statement_block elsif_clause* else_clause? "END_IF" ";"

    elsif_clause: "ELSIF" expression "THEN" statement_block

    else_clause: "ELSE" statement_block

    function_call: IDENTIFIER "(" argument_list? ")"

    argument_list: expression ("," expression)*

    ?expression: or_expression

    ?or_expression: and_expression
                  | or_expression "OR" and_expression -> or_op

    ?and_expression: comparison_expression
                   | and_expression "AND" comparison_expression -> and_op

    ?comparison_expression: add_expression
                          | comparison_expression ">" add_expression   -> gt
                          | comparison_expression "<" add_expression   -> lt
                          | comparison_expression ">=" add_expression  -> gte
                          | comparison_expression "<=" add_expression  -> lte
                          | comparison_expression "=" add_expression   -> eq
                          | comparison_expression "<>" add_expression  -> neq

    ?add_expression: mul_expression
                   | add_expression "+" mul_expression -> add
                   | add_expression "-" mul_expression -> sub

    ?mul_expression: unary_expression
                   | mul_expression "*" unary_expression -> mul
                   | mul_expression "/" unary_expression -> div

    ?unary_expression: primary_expression
                     | "NOT" unary_expression -> not_
                     | "-" unary_expression -> neg

    ?primary_expression: IDENTIFIER -> variable
                       | literal
                       | function_call
                       | "(" expression ")"

    ?literal: NUMBER -> number
            | "TRUE" -> true
            | "FALSE" -> false

    IDENTIFIER: /[a-zA-Z_][a-zA-Z0-9_]*/
    NUMBER: /\d+(\.\d+)?/

    %import common.WS
    %ignore WS
    %ignore /\/\/[^\n]*/
"""

@dataclass
class Variable:
    name: str
    type: str
    initial_value: Any = None
    is_input: bool = False
    is_output: bool = False

@dataclass
class Program:
    name: str
    variables: Dict[str, Variable]
    statements: List[Any]

class STTransformer(Transformer):
    """Transform parsed ST code into executable representation"""
    
    @v_args(inline=True)
    def program(self, name, *args):
        variables = {}
        statements = []
        
        logger.debug(f"Program args: {args}")
        
        for arg in args:
            logger.debug(f"Processing arg: {arg}")
            # Check if it's a Tree object from a declaration block
            if hasattr(arg, 'data') and arg.data == 'declaration_block':
                # Extract the dictionary from the Tree's children
                if arg.children and isinstance(arg.children[0], dict) and '_vars' in arg.children[0]:
                    logger.debug(f"Found variables in tree: {arg.children[0]['_vars']}")
                    variables.update(arg.children[0]['_vars'])
            elif isinstance(arg, dict) and '_vars' in arg:
                logger.debug(f"Found variables: {arg['_vars']}")
                variables.update(arg['_vars'])
            elif isinstance(arg, list):
                logger.debug(f"Found statements: {len(arg)} statements")
                statements = arg
        
        logger.debug(f"Total variables found: {len(variables)}")
        result = Program(name=str(name), variables=variables, statements=statements)
        logger.debug(f"Created program: {result}")
        return result

    
    def var_declarations(self, declarations):
        vars_dict = {}
        for decl in declarations:
            if isinstance(decl, dict):
                vars_dict.update(decl)
        return {'_vars': vars_dict}
    
    def var_input_declarations(self, declarations):
        vars_dict = {}
        for decl in declarations:
            if isinstance(decl, dict):
                for name, var in decl.items():
                    var.is_input = True
                    vars_dict[name] = var
        return {'_vars': vars_dict}
    
    def var_output_declarations(self, declarations):
        vars_dict = {}
        for decl in declarations:
            if isinstance(decl, dict):
                for name, var in decl.items():
                    var.is_output = True
                    vars_dict[name] = var
        return {'_vars': vars_dict}
    
    def declaration(self, items):
        name = str(items[0])
        type_name = None
        initial_value = None
        
        for item in items[1:]:
            # Extract type name - it might be a string or need extraction from a Tree
            if isinstance(item, str) and item in ['BOOL', 'INT', 'REAL', 'TIME']:
                type_name = item
            elif hasattr(item, 'children') and len(item.children) > 0:
                # It's a Tree object, extract the type name
                type_name = str(item.children[0]) if item.children else 'REAL'
            elif isinstance(item, dict) and 'init_value' in item:
                initial_value = item['init_value']
        
        # Default to REAL if type not found
        if not type_name:
            type_name = 'REAL'
            
        return {name: Variable(name=name, type=type_name, initial_value=initial_value)}
    
    def type_name(self, items):
        # Debug what we're receiving
        logger.debug(f"type_name received: {items}")
        if not items:
            logger.warning("type_name received empty items")
            return "REAL"
        return str(items[0])
    
    
    def init_value(self, items):
        return {'init_value': items[0]}
    
    def statement_block(self, statements):
        return list(statements)
    
    def assignment(self, items):
        return {'type': 'assignment', 'target': str(items[0]), 'value': items[1]}
    
    def if_statement(self, items):
        condition = items[0]
        then_block = items[1]
        elsif_clauses = []
        else_block = None
        
        for item in items[2:]:
            if isinstance(item, dict) and item.get('type') == 'elsif':
                elsif_clauses.append(item)
            elif isinstance(item, list):
                else_block = item
        
        return {
            'type': 'if',
            'condition': condition,
            'then_block': then_block,
            'elsif_clauses': elsif_clauses,
            'else_block': else_block
        }
    
    def elsif_clause(self, items):
        return {'type': 'elsif', 'condition': items[0], 'then_block': items[1]}
    
    def else_clause(self, items):
        return items[0]
    
    def function_call(self, items):
        name = str(items[0])
        args = items[1] if len(items) > 1 else []
        return {'type': 'function_call', 'name': name, 'args': args}
    
    def argument_list(self, items):
        return list(items)
    
    # Expression handlers
    @v_args(inline=True)
    def variable(self, name):
        return {'type': 'variable', 'name': str(name)}
    
    @v_args(inline=True)
    def number(self, n):
        return {'type': 'literal', 'value': float(str(n))}
    
    @v_args(inline=True)
    def true(self):
        return {'type': 'literal', 'value': True}
    
    @v_args(inline=True)
    def false(self):
        return {'type': 'literal', 'value': False}
    
    # Binary operations
    @v_args(inline=True)
    def add(self, left, right):
        return {'type': 'binary_op', 'op': '+', 'left': left, 'right': right}
    
    @v_args(inline=True)
    def sub(self, left, right):
        return {'type': 'binary_op', 'op': '-', 'left': left, 'right': right}
    
    @v_args(inline=True)
    def mul(self, left, right):
        return {'type': 'binary_op', 'op': '*', 'left': left, 'right': right}
    
    @v_args(inline=True)
    def div(self, left, right):
        return {'type': 'binary_op', 'op': '/', 'left': left, 'right': right}
    
    # Comparison operations
    @v_args(inline=True)
    def gt(self, left, right):
        return {'type': 'comparison', 'op': '>', 'left': left, 'right': right}
    
    @v_args(inline=True)
    def lt(self, left, right):
        return {'type': 'comparison', 'op': '<', 'left': left, 'right': right}
    
    @v_args(inline=True)
    def gte(self, left, right):
        return {'type': 'comparison', 'op': '>=', 'left': left, 'right': right}
    
    @v_args(inline=True)
    def lte(self, left, right):
        return {'type': 'comparison', 'op': '<=', 'left': left, 'right': right}
    
    @v_args(inline=True)
    def eq(self, left, right):
        return {'type': 'comparison', 'op': '=', 'left': left, 'right': right}
    
    @v_args(inline=True)
    def neq(self, left, right):
        return {'type': 'comparison', 'op': '<>', 'left': left, 'right': right}
    
    # Logical operations
    @v_args(inline=True)
    def or_op(self, left, right):
        return {'type': 'logical_op', 'op': 'OR', 'left': left, 'right': right}
    
    @v_args(inline=True)
    def and_op(self, left, right):
        return {'type': 'logical_op', 'op': 'AND', 'left': left, 'right': right}
    
    # Unary operations
    @v_args(inline=True)
    def not_(self, expr):
        return {'type': 'unary_op', 'op': 'NOT', 'expr': expr}
    
    @v_args(inline=True)
    def neg(self, expr):
        return {'type': 'unary_op', 'op': '-', 'expr': expr}
    
    
    def bool_type(self, items):
        return "BOOL"

    def int_type(self, items):
        return "INT"
        
    def real_type(self, items):
        return "REAL"
        
    def time_type(self, items):
        return "TIME"
    
    IDENTIFIER = str
    NUMBER = float

class STParser:
    """Parser for Structured Text (ST) language"""
    
    def __init__(self):
        self.parser = Lark(ST_GRAMMAR, parser='lalr', transformer=STTransformer())
    
    def parse(self, st_code: str) -> Optional[Program]:
        """Parse ST code and return Program object"""
        try:
            logger.info("Parsing ST code")
            result = self.parser.parse(st_code)
            logger.info(f"Successfully parsed program: {result.name}")
            return result
        except Exception as e:
            logger.error(f"Error parsing ST code: {e}")
            return None