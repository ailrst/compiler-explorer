import type {ParseFiltersAndOutputOptions} from '../../types/features/filters.interfaces.js';
import {BaseCompiler} from '../base-compiler.js';

export class C3Compiler extends BaseCompiler {
    static get key() {
        return 'boogie';
    }

    override optionsForFilter(filters: ParseFiltersAndOutputOptions, outputFilename: string) {
        return ['/timeLimit:300'];
    }
}
