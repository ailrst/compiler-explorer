import type {ParseFiltersAndOutputOptions} from '../../types/features/filters.interfaces.js';
import {BaseCompiler} from '../base-compiler.js';
import path from 'path';

export class BoogieCompiler extends BaseCompiler {
    static get key() {
        return 'boogie';
    }

    override getOutputFilename(inputFilename: string): string {
        return this.filename(path.dirname(inputFilename) + '/stdout');
    }

    override optionsForFilter(filters: ParseFiltersAndOutputOptions, outputFilename: string) {
        return [];
    }
}
